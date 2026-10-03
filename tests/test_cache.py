"""Tests for steam_news2.cache (AppNameCache)."""

from steam_news2.cache import AppNameCache


def test_app_name_cache_roundtrip(tmp_path):
    cache = AppNameCache(str(tmp_path / "apps.sqlite"))
    assert cache.load() == {}
    assert cache.fetched_at() is None

    cache.store({440: "Team Fortress 2", 570: "Dota 2"})
    assert cache.load() == {440: "Team Fortress 2", 570: "Dota 2"}
    assert cache.fetched_at() is not None
