"""Provider registry and result merging."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
from aiolimiter import AsyncLimiter

from ..base import BaseProvider
from ..config import Config
from .anilist import AniListProvider
from .mangadex import MangaDexProvider
from .myanimelist import MyAnimeListProvider
from .novelbuddy import NovelBuddyProvider
from .novelupdates import NovelUpdatesProvider
from .ranobedb import RanobeDBProvider
from .webnovel import WebnovelProvider

logger = logging.getLogger(__name__)

#: name -> provider class, in default priority order.
PROVIDERS: dict[str, type[BaseProvider]] = {
    "anilist": AniListProvider,
    "mangadex": MangaDexProvider,
    "ranobedb": RanobeDBProvider,
    "myanimelist": MyAnimeListProvider,
    "novelupdates": NovelUpdatesProvider,
    "webnovel": WebnovelProvider,
    "novelbuddy": NovelBuddyProvider,
}


def build_providers(
    config: Config,
    session: aiohttp.ClientSession,
    limiter: AsyncLimiter,
) -> list[BaseProvider]:
    """Instantiate providers in the configured priority order.

    Unknown names are skipped with a warning; disabled providers (e.g. MAL
    without a client id) are skipped silently.
    """
    providers: list[BaseProvider] = []
    for name in config.source_priority:
        cls = PROVIDERS.get(name)
        if cls is None:
            logger.warning("Unknown source in SOURCE_PRIORITY: %s", name)
            continue
        provider = cls(config, session, limiter)
        if not provider.enabled:
            logger.info("Source %s disabled (missing configuration)", name)
            continue
        providers.append(provider)
    return providers


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/whitespace for dedupe comparison."""
    return re.sub(r"[\s\W_]+", "", title.lower())


def merge_results(
    results: list[tuple[str, list[dict[str, Any]]]],
    mode: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Merge per-source results into a single ABS ``matches`` list.

    ``results`` is a list of ``(source_name, matches)`` in priority order.

    - ``priority``: round-robin interleave by source priority (one result
      from each source per round), dedupe by normalized title, keep the
      first (highest-priority) occurrence.
    - ``first``: return only the first source that produced matches.
    """
    if mode == "first":
        for _name, matches in results:
            if matches:
                return matches[:limit]
        return []

    queues = [list(matches) for _name, matches in results]
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    while len(merged) < limit:
        progressed = False
        for queue in queues:
            while queue:
                match = queue.pop(0)
                key = _normalize_title(match["title"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(match)
                progressed = True
                break
            if len(merged) >= limit:
                return merged
        if not progressed:
            break
    return merged
