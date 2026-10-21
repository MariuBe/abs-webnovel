"""NovelBuddy provider (novelbuddy.me).

NovelBuddy is a multi-site platform (MangaBuddy, NovelBuddy, …) with a plain
JSON API at ``https://api.novelbuddy.me``. The site itself is not behind
Cloudflare, so requests go directly. The search endpoint is
``GET /titles/search?q=<query>`` and returns ``{"data": {"items": [...]}}``.

The backend is occasionally unavailable (its health endpoint reports an open
database circuit and the API answers 503); in that case this source returns no
results and the other providers carry the request.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import BaseProvider, normalize_match

logger = logging.getLogger(__name__)

API_BASE = "https://api.novelbuddy.me"
COVER_BASE = "https://res.mbbcdn.com/thumb/"


class NovelBuddyProvider(BaseProvider):
    name = "novelbuddy"

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        data = await self.get_json(
            f"{API_BASE}/titles/search",
            params={"q": query},
        )
        if not data:
            return []

        items = _extract_items(data)
        matches: list[dict[str, Any]] = []
        for item in items[:limit]:
            match = self._parse(item)
            if match:
                matches.append(match)
        return matches

    def _parse(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = item.get("name")
        if not title:
            return None

        raw: dict[str, Any] = {"title": title}

        authors = _names(item.get("authors"))
        if authors:
            raw["author"] = ", ".join(authors)

        summary = item.get("summary") or item.get("description")
        if summary:
            raw["description"] = summary

        cover = item.get("cover")
        if cover:
            raw["cover"] = _cover_url(cover)

        genres = _names(item.get("genres"))
        if genres:
            raw["genres"] = genres

        tags = _names(item.get("tags"))
        if tags:
            raw["tags"] = tags

        return normalize_match(raw)


def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the item list out of the API envelope.

    The API returns ``{"data": {"items": [...]}}``; some endpoints return the
    list at the top level, so both shapes are handled.
    """
    payload = data.get("data")
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
    if isinstance(data.get("items"), list):
        return [i for i in data["items"] if isinstance(i, dict)]
    return []


def _names(value: Any) -> list[str]:
    """Coerce a list of strings or ``{"name": ...}`` objects to names."""
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            if entry.strip():
                names.append(entry.strip())
        elif isinstance(entry, dict):
            name = entry.get("name") or entry.get("title")
            if name and str(name).strip():
                names.append(str(name).strip())
    return names


def _cover_url(cover: str) -> str:
    """Build the full cover URL from the API's relative cover path."""
    cover = cover.strip()
    if cover.startswith(("http://", "https://")):
        return cover
    if cover.startswith("//"):
        return "https:" + cover
    if not cover.startswith("/"):
        cover = "/" + cover
    return COVER_BASE + cover.lstrip("/")
