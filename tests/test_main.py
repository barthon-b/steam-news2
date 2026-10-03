"""Tests for steam_news2.main (merge, resolve_app_names, and the CLI)."""

import json
import time

import pytest

from steam_news2.cache import AppNameCache
from steam_news2.main import main, merge_followed, resolve_app_names


def test_merge_dedupes_and_sorts():
    owned = {730: "Counter-Strike 2", 570: "Dota 2"}
    wishlisted = [1086940, 730]
    followed = [440, 570]
    assert merge_followed(owned, wishlisted, followed) == [
        {"appid": 440, "name": None, "sources": ["followed"]},
        {"appid": 570, "name": "Dota 2", "sources": ["followed", "owned"]},
        {"appid": 730, "name": "Counter-Strike 2", "sources": ["owned", "wishlisted"]},
        {"appid": 1086940, "name": None, "sources": ["wishlisted"]},
    ]


def test_merge_empty():
    assert merge_followed({}, [], []) == []


def test_merge_name_only_for_owned():
    assert merge_followed({}, [440], []) == [
        {"appid": 440, "name": None, "sources": ["wishlisted"]}
    ]


def test_resolve_app_names_uses_fresh_cache(tmp_path):
    cache = AppNameCache(str(tmp_path / "apps.sqlite"))
    cache.store({440: "cached"})

    class FakeClient:
        def app_names(self):
            raise AssertionError("must not hit the API when the cache is fresh")

    names = resolve_app_names(FakeClient(), cache, max_age=10**9)
    assert names == {440: "cached"}


def test_resolve_app_names_refreshes_stale_cache(tmp_path, monkeypatch):
    cache = AppNameCache(str(tmp_path / "apps.sqlite"))
    cache.store({440: "stale"})

    class FakeClient:
        def app_names(self):
            return {440: "fresh", 570: "new"}

    monkeypatch.setattr(time, "time", lambda: 10**12)
    names = resolve_app_names(FakeClient(), cache, max_age=60)
    assert names == {440: "fresh", 570: "new"}
    assert cache.load() == {440: "fresh", 570: "new"}


def test_main_missing_env_raises():
    with pytest.raises(ValueError):
        main(env={})


def test_main_resolution_error_raises():
    class FakeClient:
        def resolve_steamid(self, raw, api_key):
            raise ValueError("nope")

    with pytest.raises(ValueError):
        main(
            env={"STEAM_API_KEY": "k", "STEAM_ID": "badname"},
            client=FakeClient(),
        )


def test_main_prints_json(capsys, tmp_path):
    class FakeClient:
        def resolve_steamid(self, raw, api_key):
            return "76561198000000000"

        def owned(self, steamid, api_key):
            return {730: "Counter-Strike 2"}

        def wishlisted(self, steamid):
            return [1086940]

        def followed(self, steamid):
            return []

        def app_names(self):
            return {730: "Counter-Strike 2", 1086940: "Baldur's Gate 3"}

        def news(self, appid, count=20):
            return [{"gid": "1", "title": f"News for {appid}", "date": 1700000000}]

    main(
        env={"STEAM_API_KEY": "k", "STEAM_ID": "76561198000000000"},
        client=FakeClient(),
        cache=AppNameCache(str(tmp_path / "cache.sqlite")),
    )
    out = json.loads(capsys.readouterr().out)
    assert [(n["appid"], n["name"]) for n in out["news"]] == [
        (730, "Counter-Strike 2"),
        (1086940, "Baldur's Gate 3"),
    ]
    assert [len(n["items"]) for n in out["news"]] == [1, 1]
