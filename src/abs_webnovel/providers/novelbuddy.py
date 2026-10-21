"""NovelBuddy provider (novelbuddy.me).

NovelBuddy is a multi-site platform (MangaBuddy, NovelBuddy, …) with a plain
JSON API at ``https://api.novelbuddy.me``. The site itself is not behind
Cloudflare, so requests go directly.

The search endpoint (``GET /titles/search?q=<query>``) returns lightweight
items without authors, so for each hit we fetch the detail endpoint
(``GET /titles/<id>``) to get authors, tags and the release date — the same
search-then-detail pattern as RanobeDB.

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
            detail = await self.get_json(f"{API_BASE}/titles/{item.get('id')}")
            detail_title = (detail or {}).get("data", {}).get("title") or {}
            match = self._parse(item, detail_title)
            if match:
                matches.append(match)
        return matches

    def _parse(
        self, search_item: dict[str, Any], detail: dict[str, Any]
    ) -> dict[str, Any] | None:
        title = detail.get("name") or search_item.get("name")
        if not title:
            return None

        raw: dict[str, Any] = {"title": title}

        authors = _names(detail.get("authors"))
        if authors:
            raw["author"] = ", ".join(authors)

        summary = detail.get("summary") or search_item.get("summary")
        if summary:
            raw["description"] = summary

        cover = detail.get("cover") or search_item.get("cover")
        if cover:
            raw["cover"] = _cover_url(cover)

        genres = _names(detail.get("genres") or search_item.get("genres"))
        if genres:
            raw["genres"] = genres

        tags = _names(detail.get("tags"))
        if tags:
            raw["tags"] = tags

        year = _year(detail.get("release_date")) or _year(
            detail.get("first_chapter_updated_at")
        )
        if year:
            raw["publishedYear"] = year

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


def _year(value: Any) -> int | None:
    """Extract a year from an ISO date string (``YYYY-...``)."""
    if not value:
        return None
    try:
        return int(str(value)[:4])
    except ValueError:
        return None


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
