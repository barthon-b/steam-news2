"""Steam Web API client."""

from __future__ import annotations

import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

    def news(self, appid: int, count: int = 20) -> list[dict]:
        """Return the latest news items for ``appid``.

        Each item is ``{"gid", "title", "url", "author", "contents", "feedlabel", "date"}``.
        """
        data = self.get_json(
            "ISteamNews/GetNewsForApp/v2/", {"appid": appid, "count": count}
        )
        items = data.get("appnews", {}).get("newsitems", [])
        return [
            {
                "gid": item.get("gid"),
                "title": item.get("title"),
                "url": item.get("url"),
                "author": item.get("author"),
                "contents": item.get("contents"),
                "feedlabel": item.get("feedlabel"),
                "date": item.get("date"),
            }
            for item in items
        ]

    def app_names(self) -> dict[int, str]:
        """Return the full {appid: name} map from the Steam app list."""
        data = self.get_json("ISteamApps/GetAppList/v2/", {})
        apps = data.get("applist", {}).get("apps", [])
        return {
            int(app["appid"]): app["name"]
            for app in apps
            if app.get("appid") is not None and app.get("name")
        }
