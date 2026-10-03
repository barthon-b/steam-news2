# steam-news2

An app to retrieve and view Steam news for the games you follow on Steam.

Meant to replicate Steam's NEWS section but with added functionality.

# status

This is a work in progress.

- [x] Game retrieval
- [x] Caching for game titles
- [x] News retrieval
- [ ] Persistence for the actual news articles
- [ ] Streamlit UI

# problem

With many games owned, wishlisted, and explicitly followed, the news section gets crowded. Some updates may slip through unnoticed, some others Steam does not even display. Given the serial nature of the news feed, it's also difficult to group or filter by specific games.

# solution

This is a containerized Python app which - based on a Steam user ID provided - retrieves all games the user follows (i.e., owns, wishlisted, or explicitly followed). Then pulls the Steam news for each of those games, for a customizable period. News items are then rendered within a Streamlit UI where the user can group them by game and filter out specific games.

# future additions

* persist all news items across container restarts
* allow marking news items as read

# technology

* Modern Python; env managed with uv, linted by Ruff; typing optional for now
* Podman for OCI containerisation
* Streamlit for the UI allowing news browsing capability, grouping, sorting, etc.
* TBD storage backend for persisting previously retrieved news (sqlite, duckdb, redis being considered)

# usage

Requirements: Python 3.13+ and [uv](https://docs.astral.sh/uv/).

1. Get a free [Steam Web API key](https://steamcommunity.com/dev/apikey).
2. Set your credentials:
   ```bash
   export STEAM_API_KEY="<your-api-key>"
   export STEAM_ID="<your-steamid64>"   # or a profile vanity name
   ```
3. Run:
   ```bash
   uv run steam-news2
   ```
