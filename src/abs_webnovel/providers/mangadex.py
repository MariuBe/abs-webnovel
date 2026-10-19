"""MangaDex provider (api.mangadex.org).

MangaDex indexes webtoons, manhwa, manga and light novels. Search results
carry tags inline; author and cover art arrive via ``includes[]``.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import BaseProvider, normalize_match, pick_title

logger = logging.getLogger(__name__)

API_BASE = "https://api.mangadex.org"
COVER_BASE = "https://uploads.mangadex.org/covers"


class MangaDexProvider(BaseProvider):
    name = "mangadex"

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        data = await self.get_json(
            f"{API_BASE}/manga",
            params={
                "title": query,
                "limit": limit,
                "includes[]": ["cover_art", "author", "tag"],
            },
        )
        if not data or data.get("result") != "ok":
            return []

        matches: list[dict[str, Any]] = []
        for item in data.get("data") or []:
            match = self._parse(item)
            if match:
                matches.append(match)
        return matches

    def _parse(self, item: dict[str, Any]) -> dict[str, Any] | None:
        attrs = item.get("attributes") or {}
        manga_id = item.get("id")

        # Title: prefer English, then any alt title, then the main title map.
        title = None
        for alt in attrs.get("altTitles") or []:
            if alt.get("en"):
                title = alt["en"]
                break
        if not title:
            title = pick_title(attrs.get("title") or {}, self.config.prefer_romaji)
        if not title:
            return None

        raw: dict[str, Any] = {"title": title}

        description = attrs.get("description") or {}
        if isinstance(description, dict):
            description = description.get("en") or next(
                (v for v in description.values() if v), None
            )
        if description:
            raw["description"] = description

        if attrs.get("year"):
            raw["publishedYear"] = attrs["year"]

        # Genres from inline tags (group == "genre").
        genres = [
            (tag.get("attributes", {}).get("name") or {}).get("en")
            for tag in attrs.get("tags") or []
            if (tag.get("attributes", {}).get("group") == "genre")
        ]
        genres = [g for g in genres if g]
        if genres:
            raw["genres"] = genres

        # Author + cover from relationships.
        for rel in item.get("relationships") or []:
            rel_type = rel.get("type")
            if rel_type == "author":
                name = (rel.get("attributes") or {}).get("name")
                if name:
                    raw["author"] = name
            elif rel_type == "cover_art":
                file_name = (rel.get("attributes") or {}).get("fileName")
                if manga_id and file_name:
                    raw["cover"] = f"{COVER_BASE}/{manga_id}/{file_name}.250.jpg"

        return normalize_match(raw)
