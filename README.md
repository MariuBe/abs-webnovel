# abs-webnovel

A lightweight **custom metadata provider** for [Audiobookshelf](https://github.com/advplyr/audiobookshelf) that finds **light novel / web novel** metadata by querying several upstream sources in a **configurable priority order**:

| Source | Notes |
|---|---|
| **AniList** | Light novels are `type: MANGA, format_in: [NOVEL, MANGA]` (post-2025 schema). Authors come from the `staff` connection. |
| **MangaDex** | Webtoons, manhwa, manga and light novels. Cover/author via `includes[]`. |
| **RanobeDB** | Light-novel focused. Search + detail fetch for description, staff, publishers, series, ISBN. |
| **MyAnimeList** | Requires a client id (`MAL_CLIENT_ID`); disabled when not set. |
| **NovelUpdates** | Behind Cloudflare. Works out of the box only when a [Byparr](https://github.com/ThePhaseless/Byparr) anti-bot proxy is configured (`BYPARR_URL`); otherwise best-effort and often returns nothing. |
| **Webnovel** | webnovel.com (Qidian International). Behind Cloudflare — only active when `BYPARR_URL` is set; searches are routed through Byparr. |
| **NovelBuddy** | novelbuddy.me — plain JSON API, no Cloudflare. The upstream backend is occasionally unavailable (503); the source then simply returns nothing. |

The service exposes a single `GET /search` endpoint that matches the
Audiobookshelf **Custom Metadata Provider** contract
(`server/providers/CustomProviderAdapter.js`), so it can be added from
**Settings → Item Metadata Utils → Custom Metadata Providers**.

## How it works

1. Audiobookshelf calls `GET {url}/search?mediaType=book&query={title}&author={author}`.
2. `abs-webnovel` queries **all enabled sources in parallel** (shared rate limiter, optional SQLite response cache).
3. Results are merged according to `MERGE_MODE`:
   - `priority` (default): results are round-robin interleaved by source priority (one result from each source per round), deduplicated by normalized title. The top result always comes from the highest-priority source.
   - `first`: the highest-priority source that returns at least one match wins.
4. The response is `{"matches": [ ... ]}` with the fields ABS understands:
   `title`, `subtitle`, `author`, `narrator`, `publisher`, `publishedYear`,
   `cover`, `isbn`, `asin`, `language`, `description`, `genres`, `tags`,
   `series`, `duration`.

## Quick start (Docker)

```bash
cp .env.example .env   # then edit values (ports, source priority, proxy, …)
docker compose up -d --build
```

The `compose.yaml` file starts both `abs-webnovel` and the Byparr Cloudflare
bypass, and reads all configuration from `.env` (see
[Configuration](#configuration-environment-variables)).

Then in Audiobookshelf: **Settings → Item Metadata Utils → Custom Metadata
Providers → Add**

- **Name:** `Webnovel`
- **URL:** `http://<host>:8080/search`
- **Authorization Header Value:** *(leave empty)*

## Run locally

```bash
uv sync
uv run abs-webnovel --port 8080            # no cache
uv run abs-webnovel --cache-dir ./cache    # with SQLite response cache
```

Smoke test:

```bash
curl "http://localhost:8080/search?mediaType=book&query=solo%20leveling"
```

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind host. |
| `PORT` | `8080` | Bind port. |
| `LOG_LEVEL` | `INFO` | Logging level. |
| `SEARCH_LIMIT` | `5` | Max results per source (and in the merged response). |
| `SOURCE_PRIORITY` | `anilist,mangadex,ranobedb,myanimelist,novelupdates,webnovel,novelbuddy` | Comma-separated, ordered source list. Unknown names are ignored. |
| `MERGE_MODE` | `priority` | `priority` = merge all sources by priority; `first` = stop at the first source with results. |
| `PREFER_ROMAJI` | `true` | Prefer romaji/English titles over native (JP/KR) titles. |
| `MAL_CLIENT_ID` | *(empty)* | MyAnimeList client id. The MAL source is disabled when empty. |
| `BYPARR_URL` | *(empty)* | Base URL of a [Byparr](https://github.com/ThePhaseless/Byparr) anti-bot proxy (e.g. `http://byparr:8191`). When set, captcha-protected sources (NovelUpdates, Webnovel) are fetched through it. |
| `RATE_LIMIT` | `60` | Shared upstream request budget… |
| `RATE_PERIOD` | `60` | …per this many seconds (applied across all sources). |

`--cache-dir <dir>` enables a 7-day SQLite response cache for upstream GETs.

### Byparr (Cloudflare bypass for NovelUpdates and Webnovel)

NovelUpdates and webnovel.com sit behind Cloudflare and return 403 to plain
HTTP clients. [Byparr](https://github.com/ThePhaseless/Byparr) is a
FlareSolverr-compatible service that drives a real browser, solves the
challenge, and returns the rendered page. Point `BYPARR_URL` at a running
instance and those sources will route their requests through it.

The bundled `compose.yaml` already runs a `byparr` service and wires
`BYPARR_URL=http://byparr:8191` into `abs-webnovel`, so the bypass is enabled
out of the box. Byparr's own settings (proxy, locale, timezone) are configured
through the same `.env` file:

```yaml
# compose.yaml (already included)
byparr:
  image: ghcr.io/thephaseless/byparr:latest
  env_file: .env
  ports:
    - "${BYPARR_PORT:-8191}:8191"
  shm_size: "1gb"
  tmpfs:
    - /tmp:exec,mode=1777,size=1G
    - /cache:mode=1777,size=512M
```

Notes:

- Byparr's `cf_clearance` cookie is bound to *its* User-Agent and egress IP,
  so the request itself must go through Byparr (this service does not reuse
  the cookie in its own client).
- Byparr does not *guarantee* a bypass — success depends on the egress IP.
  A residential proxy (`PROXY_SERVER`) often improves the success rate.
- When Byparr is unreachable or the challenge fails, NovelUpdates and
  Webnovel simply return no results; the other sources are unaffected.

### Example: RanobeDB first, then AniList

```bash
SOURCE_PRIORITY=ranobedb,anilist,mangadex uv run abs-webnovel
```

## Project layout

```
src/abs_webnovel/
├── main.py            # aiohttp app, /search + /health, startup wiring
├── config.py          # env-var configuration
├── base.py            # BaseProvider, match normalization, helpers
└── providers/
    ├── __init__.py    # registry + merge/dedupe
    ├── anilist.py
    ├── mangadex.py
    ├── ranobedb.py
    ├── myanimelist.py
    ├── novelupdates.py
    ├── webnovel.py
    └── novelbuddy.py
tests/                 # unit tests (merge logic, parsers, Byparr)
    └── mock_byparr.py # local mock Byparr for smoke testing
```

## Notes & limitations

- **NovelUpdates** and **Webnovel** are Cloudflare-protected; without a
  Byparr proxy (`BYPARR_URL`) they are disabled and return nothing. They
  never block the request.
- **NovelBuddy**'s backend is occasionally down (503); the source then
  returns nothing until it recovers.
- **MyAnimeList** needs a client id from
  [myanimelist.net/apiconfig](https://myanimelist.net/apiconfig).
- Each provider swallows its own errors — one broken upstream never breaks a
  search request.
- `description` is sanitized (HTML stripped) before being returned; ABS also
  runs it through its own HTML sanitizer.

## License

MIT — see [LICENSE](./LICENSE).
