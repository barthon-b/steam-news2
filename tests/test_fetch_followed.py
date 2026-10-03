"""Tests for fetch_followed: merge logic, retry config, resolution, and CLI."""

import json

import pytest
import requests

import fetch_followed as ff


# --- test doubles ------------------------------------------------------------

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
    return ff.SteamClient(session=FakeSession(FakeResponse(payload)))


# --- merge_followed ----------------------------------------------------------

def test_merge_dedupes_and_sorts():
    owned = {730: "Counter-Strike 2", 570: "Dota 2"}
    wishlisted = [1086940, 730]
    followed = [440, 570]
    assert ff.merge_followed(owned, wishlisted, followed) == [
        {"appid": 440, "name": None, "sources": ["followed"]},
        {"appid": 570, "name": "Dota 2", "sources": ["followed", "owned"]},
        {"appid": 730, "name": "Counter-Strike 2", "sources": ["owned", "wishlisted"]},
        {"appid": 1086940, "name": None, "sources": ["wishlisted"]},
    ]


def test_merge_empty():
    assert ff.merge_followed({}, [], []) == []


def test_merge_name_only_for_owned():
    assert ff.merge_followed({}, [440], []) == [
        {"appid": 440, "name": None, "sources": ["wishlisted"]}
    ]


# --- retry configuration ------------------------------------------------------

def test_retry_config():
    client = ff.SteamClient()  # builds a real session (no network)
    adapter = client._session.get_adapter("https://api.steampowered.com/")
    retry = adapter.max_retries
    assert retry.total == ff.MAX_RETRIES
    assert set(retry.status_forcelist) == set(ff.RETRYABLE_STATUSES)
    assert retry.backoff_factor == ff.BACKOFF_BASE_SECONDS
    assert retry.respect_retry_after_header is True


# --- get_json ----------------------------------------------------------------

def test_get_json_returns_json_and_passes_kwargs():
    session = FakeSession(FakeResponse({"response": {"ok": True}}))
    client = ff.SteamClient(session=session, timeout=99)
    result = client.get_json("Some/Path/v1/", {"x": 1})
    assert result == {"response": {"ok": True}}
    url, params, headers, timeout = session.calls[0]
    assert url == "https://api.steampowered.com/Some/Path/v1/"
    assert params == {"x": 1}
    assert headers == {"User-Agent": ff.USER_AGENT}
    assert timeout == 99


def test_get_json_raises_on_http_error():
    session = FakeSession(FakeResponse(error=requests.HTTPError("403 Forbidden")))
    client = ff.SteamClient(session=session)
    with pytest.raises(requests.HTTPError):
        client.get_json("Some/Path/v1/", {})


# --- resolve_steamid ----------------------------------------------------------

def test_resolve_passthrough_steamid64():
    session = FakeSession()
    client = ff.SteamClient(session=session)
    assert client.resolve_steamid("76561198000000000", "key") == "76561198000000000"
    assert session.calls == []


def test_resolve_vanity():
    client = client_with({"response": {"success": 1, "steamid": "76561198000000000"}})
    assert client.resolve_steamid("gabelogannewell", "key") == "76561198000000000"


def test_resolve_vanity_not_found():
    client = client_with({"response": {"success": 42, "message": "No match"}})
    with pytest.raises(ValueError):
        client.resolve_steamid("nosuchuser123", "key")


# --- fetch parsing ------------------------------------------------------------

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


# --- main() -------------------------------------------------------------------

def test_main_missing_env_raises():
    with pytest.raises(ValueError):
        ff.main(env={})


def test_main_resolution_error_raises():
    class FakeClient:
        def resolve_steamid(self, raw, api_key):
            raise ValueError("nope")

    with pytest.raises(ValueError):
        ff.main(
            env={"STEAM_API_KEY": "k", "STEAM_ID": "badname"},
            client=FakeClient(),
        )


def test_main_prints_json(capsys):
    class FakeClient:
        def resolve_steamid(self, raw, api_key):
            return "76561198000000000"

        def owned(self, steamid, api_key):
            return {730: "Counter-Strike 2"}

        def wishlisted(self, steamid):
            return [1086940]

        def followed(self, steamid):
            return []

    ff.main(
        env={"STEAM_API_KEY": "k", "STEAM_ID": "76561198000000000"},
        client=FakeClient(),
    )
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 2
    assert {g["appid"] for g in out["games"]} == {730, 1086940}
