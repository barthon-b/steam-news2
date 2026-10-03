"""Tests for steam_news2.client (SteamClient)."""

import pytest
import requests

from steam_news2.client import (
    BACKOFF_BASE_SECONDS,
    MAX_RETRIES,
    RETRYABLE_STATUSES,
    USER_AGENT,
    SteamClient,
)


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response=None):
        self._response = response
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers, timeout))
        return self._response


def client_with(payload):
    return SteamClient(session=FakeSession(FakeResponse(payload)))


def test_retry_config():
    client = SteamClient()  # builds a real session (no network)
    adapter = client._session.get_adapter("https://api.steampowered.com/")
    retry = adapter.max_retries
    assert retry.total == MAX_RETRIES
    assert set(retry.status_forcelist) == set(RETRYABLE_STATUSES)
    assert retry.backoff_factor == BACKOFF_BASE_SECONDS
    assert retry.respect_retry_after_header is True


def test_get_json_returns_json_and_passes_kwargs():
    session = FakeSession(FakeResponse({"response": {"ok": True}}))
    client = SteamClient(session=session, timeout=99)
    result = client.get_json("Some/Path/v1/", {"x": 1})
    assert result == {"response": {"ok": True}}
    url, params, headers, timeout = session.calls[0]
    assert url == "https://api.steampowered.com/Some/Path/v1/"
    assert params == {"x": 1}
    assert headers == {"User-Agent": USER_AGENT}
    assert timeout == 99


def test_get_json_raises_on_http_error():
    session = FakeSession(FakeResponse(error=requests.HTTPError("403 Forbidden")))
    client = SteamClient(session=session)
    with pytest.raises(requests.HTTPError):
        client.get_json("Some/Path/v1/", {})


def test_resolve_passthrough_steamid64():
    session = FakeSession()
    client = SteamClient(session=session)
    assert client.resolve_steamid("76561198000000000", "key") == "76561198000000000"
    assert session.calls == []


def test_resolve_vanity():
    client = client_with({"response": {"success": 1, "steamid": "76561198000000000"}})
    assert client.resolve_steamid("gabelogannewell", "key") == "76561198000000000"


def test_resolve_vanity_not_found():
    client = client_with({"response": {"success": 42, "message": "No match"}})
    with pytest.raises(ValueError):
        client.resolve_steamid("nosuchuser123", "key")


def test_owned_parses():
    client = client_with(
        {"response": {"game_count": 1, "games": [{"appid": 730, "name": "CS2"}]}}
    )
    assert client.owned("76561198000000000", "k") == {730: "CS2"}


def test_owned_raises_on_private():
    client = client_with({"response": {}})
    with pytest.raises(RuntimeError):
        client.owned("76561198000000000", "k")


def test_wishlisted_parses():
    client = client_with({"response": {"items": [{"appid": 440}, {"appid": 570}]}})
    assert client.wishlisted("76561198000000000") == [440, 570]


def test_followed_parses():
    client = client_with({"response": {"appids": [730, 1086940]}})
    assert client.followed("76561198000000000") == [730, 1086940]


def test_news_parses():
    client = client_with(
        {
            "appnews": {
                "newsitems": [
                    {
                        "gid": "1",
                        "title": "Update",
                        "url": "https://store.steampowered.com/news/1",
                        "author": "dev",
                        "contents": "<p>hi</p>",
                        "feedlabel": "Community Announcements",
                        "date": 1700000000,
                    }
                ]
            }
        }
    )
    assert client.news(730, count=2) == [
        {
            "gid": "1",
            "title": "Update",
            "url": "https://store.steampowered.com/news/1",
            "author": "dev",
            "contents": "<p>hi</p>",
            "feedlabel": "Community Announcements",
            "date": 1700000000,
        }
    ]


def test_app_names_parses():
    client = client_with(
        {"applist": {"apps": [{"appid": 440, "name": "Team Fortress 2"}, {"appid": 570, "name": "Dota 2"}]}}
    )
    assert client.app_names() == {440: "Team Fortress 2", 570: "Dota 2"}
