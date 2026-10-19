# abs-webnovel

A lightweight **custom metadata provider** for [Audiobookshelf](https://github.com/advplyr/audiobookshelf) that finds **light novel / web novel** metadata by querying several upstream sources in a **configurable priority order**:

| Source | Notes |
|---|---|
| **AniList** | Light novels are `type: MANGA, format_in: [NOVEL, MANGA]` (post-2025 schema). Authors come from the `staff` connection. |
| **MangaDex** | Webtoons, manhwa, manga and light novels. Cover/author via `includes[]`. |
| **RanobeDB** | Light-novel focused. Search + detail fetch for description, staff, publishers, series, ISBN. |
| **MyAnimeList** | Requires a client id (`MAL_CLIENT_ID`); disabled when not set. |
| **NovelUpdates** | Behind Cloudflare. Works out of the box only when a [Byparr](https://github.com/ThePhaseless/Byparr) anti-bot proxy is configured (`BYPARR_URL`); otherwise best-effort and often returns nothing. |

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
docker compose up -d --build
```

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
| `SOURCE_PRIORITY` | `anilist,mangadex,ranobedb,myanimelist,novelupdates` | Comma-separated, ordered source list. Unknown names are ignored. |
| `MERGE_MODE` | `priority` | `priority` = merge all sources by priority; `first` = stop at the first source with results. |
| `PREFER_ROMAJI` | `true` | Prefer romaji/English titles over native (JP/KR) titles. |
| `MAL_CLIENT_ID` | *(empty)* | MyAnimeList client id. The MAL source is disabled when empty. |
| `BYPARR_URL` | *(empty)* | Base URL of a [Byparr](https://github.com/ThePhaseless/Byparr) anti-bot proxy (e.g. `http://byparr:8191`). When set, captcha-protected sources (NovelUpdates) are fetched through it. |
| `RATE_LIMIT` | `60` | Shared upstream request budget… |
| `RATE_PERIOD` | `60` | …per this many seconds (applied across all sources). |

`--cache-dir <dir>` enables a 7-day SQLite response cache for upstream GETs.

### Byparr (Cloudflare bypass for NovelUpdates)

NovelUpdates sits behind Cloudflare and returns 403 to plain HTTP clients.
[Byparr](https://github.com/ThePhaseless/Byparr) is a FlareSolverr-compatible
service that drives a real browser, solves the challenge, and returns the
rendered page. Point `BYPARR_URL` at a running instance and the NovelUpdates
source will route its requests through it:

```yaml
# compose.yaml (add alongside the abs-webnovel service)
byparr:
  image: ghcr.io/thephaseless/byparr:latest
  ports:
    - "8191:8191"
  shm_size: "1gb"
  tmpfs:
    - /tmp:exec,mode=1777,size=1G
    - /cache:mode=1777,size=512M

abs-webnovel:
  # ...
  environment:
    BYPARR_URL: "http://byparr:8191"
```

Notes:

- Byparr's `cf_clearance` cookie is bound to *its* User-Agent and egress IP,
  so the request itself must go through Byparr (this service does not reuse
  the cookie in its own client).
- Byparr does not *guarantee* a bypass — success depends on the egress IP.
  A residential proxy (`PROXY_SERVER`) often improves the success rate.
- When Byparr is unreachable or the challenge fails, NovelUpdates simply
  returns no results; the other sources are unaffected.

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
    └── novelupdates.py
tests/                 # unit tests (merge logic, parsers, Byparr)
    └── mock_byparr.py # local mock Byparr for smoke testing
```

## Notes & limitations

- **NovelUpdates** is Cloudflare-protected; without a Byparr proxy
  (`BYPARR_URL`) expect it to return nothing from most server environments.
  It never blocks the request.
- **MyAnimeList** needs a client id from
  [myanimelist.net/apiconfig](https://myanimelist.net/apiconfig).
- Each provider swallows its own errors — one broken upstream never breaks a
  search request.
- `description` is sanitized (HTML stripped) before being returned; ABS also
  runs it through its own HTML sanitizer.

## License

MIT — see [LICENSE](./LICENSE).
