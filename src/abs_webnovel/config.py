"""Runtime configuration for abs-webnovel.

Everything is driven by environment variables so the service can be tuned
without code changes (e.g. inside a container). See README.md for the full
list and defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


@dataclass
class Config:
    """Parsed, validated configuration for the service."""

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"

    # How many results each upstream source should return.
    search_limit: int = 5

    # Comma-separated, ordered list of source names. Earlier = higher priority.
    source_priority: list[str] = field(
        default_factory=lambda: [
            "anilist",
            "mangadex",
            "ranobedb",
            "myanimelist",
            "novelupdates",
            "webnovel",
            "novelbuddy",
        ]
    )

    # "priority": query every enabled source in parallel, then merge the
    #   results ordered by source priority (deduped by normalized title).
    # "first": query sources in priority order and stop at the first one that
    #   returns at least one match.
    merge_mode: str = "priority"

    # Prefer romaji titles over native (Japanese/Korean) titles when both exist.
    prefer_romaji: bool = True

    # MyAnimeList requires a client id. Leave empty to disable that source.
    mal_client_id: str = ""

    # Optional Byparr (FlareSolverr-compatible) anti-bot proxy base URL, e.g.
    # "http://byparr:8191". When set, captcha-protected sources (NovelUpdates,
    # Webnovel) are fetched through it instead of directly. Empty = off.
    byparr_url: str = ""

    # Shared rate limit applied across all upstream requests.
    rate_limit: int = 60
    rate_period: float = 60.0

    # Optional SQLite response cache directory (passed via --cache-dir).
    cache_dir: str | None = None

    @classmethod
    def from_env(cls) -> Config:
        priority_raw = os.environ.get("SOURCE_PRIORITY", "").strip()
        if priority_raw:
            priority = [p.strip().lower() for p in priority_raw.split(",") if p.strip()]
        else:
            priority = [
                "anilist",
                "mangadex",
                "ranobedb",
                "myanimelist",
                "novelupdates",
                "webnovel",
                "novelbuddy",
            ]

        merge_mode = os.environ.get("MERGE_MODE", "priority").strip().lower()
        if merge_mode not in {"priority", "first"}:
            merge_mode = "priority"

        return cls(
            host=os.environ.get("HOST", "0.0.0.0"),
            port=_env_int("PORT", 8080),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            search_limit=_env_int("SEARCH_LIMIT", 5),
            source_priority=priority,
            merge_mode=merge_mode,
            prefer_romaji=_env_bool("PREFER_ROMAJI", True),
            mal_client_id=os.environ.get("MAL_CLIENT_ID", "").strip(),
            byparr_url=os.environ.get("BYPARR_URL", "").strip().rstrip("/"),
            rate_limit=_env_int("RATE_LIMIT", 60),
            rate_period=float(os.environ.get("RATE_PERIOD", "60")),
        )
