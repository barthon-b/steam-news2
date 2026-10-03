# steam-news2

An app to retrieve and view Steam news for the games you follow on Steam.

Meant to replicate Steam's NEWS section but with added functionality.

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