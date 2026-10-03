# AGENTS.md — steam-news2

Guidance for AI coding agents (and human contributors) working in this repository.

## Project purpose

`steam-news2` is a **containerized Python app** that retrieves and renders Steam
news for the games a user follows, meant to replicate Steam's NEWS section with
added functionality.

The problem it solves: with many games owned, wishlisted, and explicitly
followed, the news feed gets crowded; updates slip through unnoticed or are never
displayed, and the serial feed can't be grouped or filtered by game.

Pipeline:

1. Given a Steam user ID, retrieve every game the user follows.
2. Pull the Steam news for each of those games, for a **customizable period**.
3. Render the news in a **Streamlit** UI where the user can **group by game** and
   **filter out specific games**.

"Following", for this project, is the **union of three distinct Steam data sets**:

1. **Owned games** — purchased or otherwise activated.
2. **Wishlisted games** — added to the Steam wishlist.
3. **Manually followed games** — the explicit "Follow" button on a store/hub page,
   separate from both owning and wishlisting.

These three lists overlap, so they must be de-duplicated (a game you own is
frequently also wishlisted/followed).

## Repository state

- Language: **Python** (the `.gitignore` is Python-oriented: `venv`, `pytest`,
  `uv`/`poetry`, `Ruff`).
- Current contents: `fetch_followed.py` (the fetcher), `tests/test_fetch_followed.py`
  (pytest suite), `pyproject.toml` (uv manifest with a `dev` dependency group),
  plus `README.md`, `LICENSE`, `.gitignore`, `AGENTS.md`. `main.py` is the
  default `uv init` stub.
- Remote: `git@github.com:barthon-b/steam-news2.git`, branch `main`.

## Technology stack

- **Modern Python**; environment managed with **uv**; linted by **Ruff**.
  Typing is **optional for now** — do not block work on type-hint coverage.
- **Podman** for OCI containerisation (use Podman, not Docker, in scripts and docs).
- **Streamlit** for the UI (news browsing, grouping, sorting, filtering).
- **Storage backend: TBD** — sqlite, duckdb, and redis are being considered for
  persisting previously retrieved news.

## Planned features

- Group news items by game; filter out specific games.
- Customizable news-retrieval period.

Future additions (from README):

- Persist all news items across container restarts.
- Allow marking news items as read.

## Commands

- `uv run fetch_followed.py` — run the fetcher (reads `STEAM_API_KEY` and `STEAM_ID`).
- `uv run pytest` — run the test suite (pytest is in the `dev` dependency group).
- `uv run ruff check .` — lint (once Ruff is added as a dev dependency).

Note: in sandboxed/CI environments where the default `~/.cache/uv` is not
writable, set `UV_CACHE_DIR` to a writable location.

## Domain knowledge: Steam data sources

This section captures verified research; it is expensive to re-derive, so read it
before touching any code that talks to Steam. All endpoints live on
`https://api.steampowered.com/`.

### The three "following" sources

| Source | Endpoint | Needs API key? | App IDs in response |
| --- | --- | --- | --- |
| Owned games | `IPlayerService/GetOwnedGames/v1/` | **yes** | `response.games[].appid` |
| Wishlist | `IWishlistService/GetWishlist/v1/` | no | `response.items[].appid` |
| Followed games | `IStoreService/GetGamesFollowed/v1/` | no | `response.appids[]` |

Request parameters:

- `GetOwnedGames/v1/`: `key`, `steamid` (SteamID64), and **always**
  `include_appinfo=true` and `include_played_free_games=true`. Without
  `include_played_free_games`, free-to-play games the user has played are
  silently omitted. Response also carries `response.game_count`.
- `GetWishlist/v1/`: `steamid`. Items carry `priority` (1 = top of list) and
  `date_added`.
- `GetGamesFollowed/v1/`: `steamid`. For large follow lists, cross-check the true
  total against the companion endpoint
  `IStoreService/GetGamesFollowedCount/v1/` → `response.followed_game_count`.
  The list may be truncated.

### Per-game news (after you have the app IDs)

- `ISteamNews/GetNewsForApp/v2/?appid=<id>&count=<n>&maxlength=<chars>` — keyless.
  Each item carries a `date` (unix timestamp); the "customizable period" is
  implemented by filtering items by that date (the endpoint has no date-range
  parameter).

### Credentials

- **SteamID64** (17-digit account number) — required for every call above.
- **Steam Web API key** — required only for owned games. Free at
  `https://steamcommunity.com/dev/apikey`.
- Never commit either. Put them in a `.env` (already git-ignored) and load via a
  library such as `python-dotenv`.

### Gotchas (must be handled, not glossed over)

1. **"Empty" is ambiguous.** All three endpoints return an empty list both when
   the profile is **private** and when it is **genuinely empty**. There is no
   error or flag distinguishing them. Code must not misreport a private profile
   as "following nothing" — surface the privacy requirement to the user instead.
2. **Privacy settings** the account must satisfy for a complete result:
   - Owned games → Profile → Edit Profile → Privacy Settings → **Game details = Public**.
   - Wishlist / followed → profile and wishlist visibility must be **Public**.
3. **Undocumented endpoints.** `IWishlistService/*` and `IStoreService/*` are
   **not** in Valve's public Steamworks Web API documentation — they are what the
   Steam client itself calls. They have been stable for years but may change
   without notice. `GetOwnedGames` and `GetNewsForApp` *are* documented.
4. **No single "feed" endpoint exists.** There is no API that returns the
   followed-games list for the news feed directly; the union of the three
   sources above is the mechanism.

## Conventions

- **Python** via **uv**; standard library preferred, add third-party deps only
  with justification (`requests` or `httpx` for HTTP is acceptable).
- Keep the Steam API key and SteamID64 out of source; read from environment.
- Respect Steam's endpoints: be conservative with request rate, add retries with
  backoff for transient 5xx/rate-limit responses, and distinguish "private/empty"
  from "request failed" in error messages.
- Use Podman for any container tooling.

## References

- Steam Web API docs: https://partner.steamgames.com/doc/webapi
- API key signup: https://steamcommunity.com/dev/apikey
- SteamID64 lookup: https://steamid.io
