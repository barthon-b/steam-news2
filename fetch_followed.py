#!/usr/bin/env python3
"""Retrieve the Steam app IDs (and names, where available) of games a user follows.

"Followed" here means the union of three Steam data sets:
  * owned games             — IPlayerService/GetOwnedGames/v1/
  * wishlisted games        — IWishlistService/GetWishlist/v1/
  * explicitly followed     — IStoreService/GetGamesFollowed/v1/

Credentials are read from environment variables:
  STEAM_API_KEY   Steam Web API key (https://steamcommunity.com/dev/apikey)
  STEAM_ID        17-digit SteamID64, or a profile vanity name (auto-resolved)

"""

from __future__ import annotations

import email.utils
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

API_BASE = "https://api.steampowered.com/"
STEAMID64_RE = re.compile(r"^\d{17}$")
TIMEOUT = 30  # seconds, per request attempt
USER_AGENT = "steam-news2/0.1"

MAX_RETRIES = 2  # retries after the initial attempt => up to 3 attempts per call
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
BACKOFF_BASE_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 60  # cap on an explicit Retry-After wait


def _parse_retry_after(value: str) -> float | None:
    """Return the wait in seconds from a Retry-After header, or None if unparseable."""
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        retry_at = email.utils.parsedate_to_datetime(value)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    """Seconds to wait before the next attempt; honours Retry-After when present."""
    retry_after = exc.headers.get("Retry-After")
    if retry_after is not None:
        seconds = _parse_retry_after(retry_after)
        if seconds is not None:
            return min(seconds, MAX_RETRY_AFTER_SECONDS)
    return BACKOFF_BASE_SECONDS * (2 ** attempt)


def _get_json(path: str, params: dict) -> dict:
    """GET ``path`` and decode JSON, retrying transient failures.

    Retries HTTP 429/5xx and network errors up to MAX_RETRIES times. Any
    non-transient error (e.g. 403 for a bad key) and any error that survives the
    retries is re-raised unchanged so the caller sees the real exception.
    """
    url = f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in RETRYABLE_STATUSES and attempt < MAX_RETRIES:
                delay = _retry_delay(exc, attempt)
                logger.warning(
                    "HTTP %s from %s; retrying in %.0fs (retry %d/%d)",
                    exc.code, path, delay, attempt + 1, MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            raise
        except OSError as exc:
            # URLError, connection errors, and timeouts are all OSError subclasses.
            if attempt < MAX_RETRIES:
                delay = BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "network error from %s (%s); retrying in %.0fs (retry %d/%d)",
                    path, exc, delay, attempt + 1, MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            raise
    raise AssertionError("unreachable")


def _resolve_steamid(raw: str, api_key: str) -> str:
    if STEAMID64_RE.fullmatch(raw):
        return raw
    data = _get_json(
        "ISteamUser/ResolveVanityURL/v1/", {"key": api_key, "vanityurl": raw}
    )
    response = data.get("response", {})
    if response.get("success") == 1 and response.get("steamid"):
        return response["steamid"]
    raise SystemExit(f"Could not resolve '{raw}' to a SteamID64.")


def fetch_owned(steamid: str, api_key: str) -> tuple[dict, bool]:
    """Return {appid: name} for owned games, plus whether the profile looked private."""
    data = _get_json(
        "IPlayerService/GetOwnedGames/v1/",
        {
            "key": api_key,
            "steamid": steamid,
            "include_appinfo": "1",
            "include_played_free_games": "1",
        },
    )
    response = data.get("response", {})
    games = response.get("games", [])
    # Steam answers an empty object (no `game_count` and no `games`) for a
    # private profile, which is indistinguishable from owning nothing — flag it.
    private = "game_count" not in response and "games" not in response
    owned = {int(game["appid"]): game.get("name") for game in games if game.get("appid") is not None}
    return owned, private


def fetch_wishlist(steamid: str) -> list[int]:
    data = _get_json("IWishlistService/GetWishlist/v1/", {"steamid": steamid})
    items = data.get("response", {}).get("items", [])
    return [int(item["appid"]) for item in items if item.get("appid") is not None]


def fetch_followed(steamid: str) -> list[int]:
    data = _get_json("IStoreService/GetGamesFollowed/v1/", {"steamid": steamid})
    return [int(appid) for appid in data.get("response", {}).get("appids", [])]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    api_key = os.environ.get("STEAM_API_KEY", "").strip()
    raw_steamid = os.environ.get("STEAM_ID", "").strip()
    if not api_key or not raw_steamid:
        logger.error("both STEAM_API_KEY and STEAM_ID environment variables are required")
        logger.error("  STEAM_API_KEY  Steam Web API key (https://steamcommunity.com/dev/apikey)")
        logger.error("  STEAM_ID       17-digit SteamID64, or a profile vanity name")
        return 2

    steamid = _resolve_steamid(raw_steamid, api_key)
    logger.info("SteamID64: %s", steamid)

    sources: dict[int, set] = {}  # appid -> set of source labels
    names: dict[int, str | None] = {}  # appid -> name (only owned provides one)

    owned, owned_private = fetch_owned(steamid, api_key)
    for appid, name in owned.items():
        sources.setdefault(appid, set()).add("owned")
        names[appid] = name
    logger.info("owned games: %d", len(owned))
    if owned_private:
        logger.warning("owned games returned empty (game details may be private)")

    wishlist = fetch_wishlist(steamid)
    for appid in wishlist:
        sources.setdefault(appid, set()).add("wishlist")
        names.setdefault(appid, None)
    logger.info("wishlisted games: %d", len(wishlist))
    if not wishlist:
        logger.warning("wishlist returned empty (wishlist/profile may be private)")

    followed = fetch_followed(steamid)
    for appid in followed:
        sources.setdefault(appid, set()).add("followed")
        names.setdefault(appid, None)
    logger.info("explicitly followed games: %d", len(followed))
    if not followed:
        logger.warning("followed games returned empty (profile may be private)")

    games = [
        {
            "appid": appid,
            "name": names.get(appid),
            "sources": sorted(sources[appid]),
        }
        for appid in sorted(sources)
    ]

    print(json.dumps({"count": len(games), "games": games}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
