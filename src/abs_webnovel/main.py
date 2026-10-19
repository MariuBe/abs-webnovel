"""abs-webnovel: multi-source light novel / web novel metadata provider.

A small sidecar service that Audiobookshelf can use as a *Custom Metadata
Provider*. It queries several upstream sources (AniList, MangaDex, RanobeDB,
MyAnimeList, NovelUpdates) in a configurable priority order and returns a
single ``{"matches": [...]}`` payload conforming to the ABS
``CustomProviderAdapter`` contract.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

import aiohttp
from aiohttp import web
from aiolimiter import AsyncLimiter

from .config import Config
from .providers import build_providers, merge_results

logger = logging.getLogger("abs_webnovel")


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # Quiet down noisy libraries.
    logging.getLogger("aiohttp_client_cache").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _make_session(config: Config, cache_dir: str | None) -> aiohttp.ClientSession:
    """Create the shared HTTP session, optionally backed by a SQLite cache."""
    if not cache_dir:
        return aiohttp.ClientSession()

    from aiohttp_client_cache import CachedSession, SQLiteBackend

    os.makedirs(cache_dir, exist_ok=True)
    backend = SQLiteBackend(
        os.path.join(cache_dir, "cache.sqlite"),
        expire_after=7 * 24 * 3600,  # 7 days
    )
    return CachedSession(
        cache=backend,
        allowed_codes=(200,),
        allowed_methods=("GET",),
    )


async def _on_startup(app: web.Application) -> None:
    config: Config = app["config"]
    limiter = AsyncLimiter(config.rate_limit, config.rate_period)
    app["session"] = _make_session(config, config.cache_dir)
    app["providers"] = app["build_providers"](config, app["session"], limiter)
    logger.info(
        "Sources enabled (priority order): %s",
        ", ".join(p.name for p in app["providers"]) or "(none)",
    )


async def _on_cleanup(app: web.Application) -> None:
    await app["session"].close()


async def _search(request: web.Request) -> web.Response:
    """GET /search?mediaType=book&query=...&author=...&isbn=..."""
    query = (request.query.get("query") or "").strip()
    author = (request.query.get("author") or "").strip() or None
    if not query:
        return web.json_response({"matches": []})

    config: Config = request.app["config"]
    providers: list = request.app["providers"]

    # Query every enabled source in parallel; each swallows its own errors.
    results = await asyncio.gather(*(p.search(query, author=author) for p in providers))
    merged = merge_results(
        list(zip((p.name for p in providers), results)),
        mode=config.merge_mode,
        limit=config.search_limit,
    )
    return web.json_response({"matches": merged})


async def _health(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "status": "ok",
            "sources": [p.name for p in request.app["providers"]],
        }
    )


def create_app(
    config: Config,
    build_providers: Any = build_providers,
) -> web.Application:
    app = web.Application()
    app["config"] = config
    app["build_providers"] = build_providers
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    app.router.add_get("/search", _search)
    app.router.add_get("/health", _health)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-source light novel / web novel metadata provider "
        "for Audiobookshelf."
    )
    parser.add_argument(
        "--host", default=None, help="Bind host (default: $HOST or 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Bind port (default: $PORT or 8080)"
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Directory for the SQLite response cache (disables caching when omitted)",
    )
    args = parser.parse_args()

    config = Config.from_env()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.cache_dir:
        config.cache_dir = args.cache_dir

    _setup_logging(config.log_level)
    app = create_app(config)
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
