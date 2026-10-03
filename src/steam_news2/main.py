#!/usr/bin/env python3
"""Retrieve Steam news for the games a user follows (owned, wishlisted, or followed).

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
import time

from steam_news2.cache import APP_CACHE_PATH, APP_LIST_MAX_AGE_SECONDS, AppNameCache
from steam_news2.client import SteamClient

logger = logging.getLogger(__name__)


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


def resolve_app_names(
    client: SteamClient, cache: AppNameCache, max_age: int = APP_LIST_MAX_AGE_SECONDS
) -> dict[int, str]:
    """Return {appid: name}, from the cache when fresh, else fetch and store."""
    fetched_at = cache.fetched_at()
    if fetched_at is not None and time.time() - fetched_at < max_age:
        names = cache.load()
        logger.info("app names loaded from cache (%d apps)", len(names))
        return names
    names = client.app_names()
    cache.store(names)
    logger.info("app names refreshed from Steam (%d apps)", len(names))
    return names


def main(env=None, client: SteamClient | None = None, cache: AppNameCache | None = None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if env is None:
        env = os.environ
    api_key = env.get("STEAM_API_KEY", "").strip()
    raw_steamid = env.get("STEAM_ID", "").strip()
    if not api_key or not raw_steamid:
        raise ValueError("STEAM_API_KEY and STEAM_ID environment variables are required")

    if client is None:
        client = SteamClient()
    if cache is None:
        cache = AppNameCache(env.get("STEAM_APP_CACHE_PATH", APP_CACHE_PATH))

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
    names = resolve_app_names(client, cache)

    # TEMPORARY test limit: two apps, two items each — remove before shipping.
    news = [
        {
            "appid": game["appid"],
            "name": names.get(game["appid"]) or game["name"],
            "items": client.news(game["appid"], count=2),
        }
        for game in games[:2]
    ]

    print(json.dumps({"news": news}, indent=2))


if __name__ == "__main__":
    main()
