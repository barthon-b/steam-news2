"""SQLite-backed cache of the Steam app-name list."""

from __future__ import annotations

import contextlib
import sqlite3
import time

APP_CACHE_PATH = "steam_apps.sqlite"
APP_LIST_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # refresh the app-name list weekly


class AppNameCache:
    """SQLite-backed {appid: name} cache, refreshed from the Steam app list."""

    def __init__(self, path: str):
        self._path = path

    def load(self) -> dict[int, str]:
        """Return the cached {appid: name} map, or {} when not yet populated."""
        with contextlib.closing(sqlite3.connect(self._path)) as conn:
            try:
                rows = conn.execute("SELECT appid, name FROM apps").fetchall()
            except sqlite3.OperationalError:
                return {}
        return dict(rows)

    def store(self, names: dict[int, str]) -> None:
        """Replace the cache with ``names`` and stamp ``fetched_at``."""
        with contextlib.closing(sqlite3.connect(self._path)) as conn:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS apps "
                    "(appid INTEGER PRIMARY KEY, name TEXT NOT NULL)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS meta "
                    "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                conn.execute("DELETE FROM apps")
                conn.executemany(
                    "INSERT INTO apps (appid, name) VALUES (?, ?)", names.items()
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('fetched_at', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(int(time.time())),),
                )

    def fetched_at(self) -> int | None:
        """Epoch seconds of the last successful store, or None."""
        with contextlib.closing(sqlite3.connect(self._path)) as conn:
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = 'fetched_at'"
                ).fetchone()
            except sqlite3.OperationalError:
                return None
        return int(row[0]) if row else None
