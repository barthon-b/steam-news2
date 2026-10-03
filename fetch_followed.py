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

import json
import logging
import os
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

API_BASE = "https://api.steampowered.com/"
STEAMID64_RE = re.compile(r"^\d{17}$")
TIMEOUT = 30  # seconds, per request attempt
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

MAX_RETRIES = 2  # retries after the initial attempt => up to 3 attempts per call
RETRYABLE_STATUSES = (429, 500, 502, 503, 504)
BACKOFF_BASE_SECONDS = 1.0


def merge_followed(owned: dict, wishlisted: list, followed: list) -> list[dict]:
    """Merge owned/wishlisted/followed app IDs into one deduplicated, sorted list.

    ``owned`` is a ``{appid: name}`` mapping (names are only available for owned
    games); ``wishlisted`` and ``followed`` are iterables of app IDs. Returns a list
    of dicts ``{"appid", "name", "sources"}`` sorted by appid ascending. ``name``
    is ``None`` unless the game is owned; ``sources`` lists every set it belongs to.
    """
    sources: dict[int, set] = {}
    names: dict[int, str | None] = {}

    for appid, name in owned.items():
        sources.setdefault(appid, set()).add("owned")
        names[appid] = name

    for appid in wishlisted:
        sources.setdefault(appid, set()).add("wishlisted")
        names.setdefault(appid, None)

    for appid in followed:
        sources.setdefault(appid, set()).add("followed")
        names.setdefault(appid, None)

    return [
        {"appid": appid, "name": names.get(appid), "sources": sorted(sources[appid])}
        for appid in sorted(sources)
    ]


class SteamClient:
    """Steam Web API client backed by a ``requests.Session`` with retries."""

    def __init__(self, session: requests.Session | None = None, timeout: int = TIMEOUT):
        self._session = session if session is not None else self._build_session()
        self.timeout = timeout

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        # urllib3 honours the Retry-After header by default.
        retry = Retry(
            total=MAX_RETRIES,
            status_forcelist=RETRYABLE_STATUSES,
            backoff_factor=BACKOFF_BASE_SECONDS,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def get_json(self, path: str, params: dict) -> dict:
        """GET ``path`` and return the decoded JSON body.

        Retries/backoff are handled by the session's urllib3 adapter; non-2xx
        responses raise via ``raise_for_status`` and propagate unchanged.
        """
        response = self._session.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def resolve_steamid(self, raw: str, api_key: str) -> str:
        """Return a SteamID64 for ``raw`` (already a SteamID64, or a vanity name)."""
        if STEAMID64_RE.fullmatch(raw):
            return raw
        data = self.get_json(
            "ISteamUser/ResolveVanityURL/v1/", {"key": api_key, "vanityurl": raw}
        )
        response = data.get("response", {})
        if response.get("success") == 1 and response.get("steamid"):
            return response["steamid"]
        raise ValueError(f"could not resolve '{raw}' to a SteamID64")

    def owned(self, steamid: str, api_key: str) -> dict:
        """Return {appid: name} for owned games.

        Raises ``RuntimeError`` when Steam answers an empty object (no
        ``game_count`` and no ``games``), which happens for a private profile.
        """
        data = self.get_json(
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
        if "game_count" not in response and "games" not in response:
            raise RuntimeError("owned games not returned; game details are likely private")
        return {int(game["appid"]): game.get("name") for game in games if game.get("appid") is not None}

    def wishlisted(self, steamid: str) -> list[int]:
        data = self.get_json("IWishlistService/GetWishlist/v1/", {"steamid": steamid})
        items = data.get("response", {}).get("items", [])
        return [int(item["appid"]) for item in items if item.get("appid") is not None]

    def followed(self, steamid: str) -> list[int]:
        data = self.get_json("IStoreService/GetGamesFollowed/v1/", {"steamid": steamid})
        return [int(appid) for appid in data.get("response", {}).get("appids", [])]


def main(env=None, client: SteamClient | None = None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if env is None:
        env = os.environ
    api_key = env.get("STEAM_API_KEY", "").strip()
    raw_steamid = env.get("STEAM_ID", "").strip()
    if not api_key or not raw_steamid:
        raise ValueError("STEAM_API_KEY and STEAM_ID environment variables are required")

    if client is None:
        client = SteamClient()

    steamid = client.resolve_steamid(raw_steamid, api_key)
    logger.info("SteamID64: %s", steamid)

    owned = client.owned(steamid, api_key)
    wishlisted = client.wishlisted(steamid)
    followed = client.followed(steamid)

    logger.info("owned games: %d", len(owned))
    logger.info("wishlisted games: %d", len(wishlisted))
    if not wishlisted:
        logger.warning("wishlisted games returned empty (wishlist/profile may be private)")
    logger.info("explicitly followed games: %d", len(followed))
    if not followed:
        logger.warning("followed games returned empty (profile may be private)")

    games = merge_followed(owned, wishlisted, followed)
    print(json.dumps({"count": len(games), "games": games}, indent=2))


if __name__ == "__main__":
    main()
