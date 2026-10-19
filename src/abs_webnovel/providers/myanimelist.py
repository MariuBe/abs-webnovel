"""MyAnimeList provider (api.myanimelist.net).

Requires a client id (``MAL_CLIENT_ID`` env var). The source is disabled when
no client id is configured.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import BaseProvider, normalize_match

logger = logging.getLogger(__name__)

API_BASE = "https://api.myanimelist.net/v2"


class MyAnimeListProvider(BaseProvider):
    name = "myanimelist"

    @property
    def enabled(self) -> bool:
        return bool(self.config.mal_client_id)

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        data = await self.get_json(
            f"{API_BASE}/manga",
            params={
                "q": query,
                "limit": limit,
                "fields": "title,main_picture,alternative_titles,"
                "num_chapters,num_volumes,author,publication_demographics,"
                "start_date,end_date,status",
            },
            headers={"X-MAL-CLIENT-ID": self.config.mal_client_id},
        )
        if not data:
            return []

        matches: list[dict[str, Any]] = []
        for item in data.get("data") or []:
            match = self._parse(item)
            if match:
                matches.append(match)
        return matches

    def _parse(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = item.get("title")
        if not title:
            return None

        raw: dict[str, Any] = {"title": title}

        picture = item.get("main_picture") or {}
        cover = picture.get("large_image_url") or picture.get("image_url")
        if cover:
            raw["cover"] = cover

        authors = [a.get("name") for a in item.get("author") or [] if a.get("name")]
        if authors:
            raw["author"] = ", ".join(authors)

        start_date = item.get("start_date")
        if start_date:
            raw["publishedYear"] = int(str(start_date)[:4])

        # Demographics double as genres (shounen, josei, ...).
        demographics = item.get("publication_demographics") or []
        if demographics:
            raw["genres"] = demographics

        return normalize_match(raw)
