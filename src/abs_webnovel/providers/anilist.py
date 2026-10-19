"""AniList provider (graphql.anilist.co).

Since the 2025 schema change, light novels are queried as
``type: MANGA`` with ``format_in: [NOVEL, MANGA]``. Authors are no longer a
direct field; they come from the ``staff`` connection (role "Original Story"
etc.).
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import BaseProvider, normalize_match, pick_title

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://graphql.anilist.co"

SEARCH_QUERY = """
query($search: String, $perPage: Int) {
  Page(page: 1, perPage: $perPage) {
    media(search: $search, type: MANGA, format_in: [NOVEL, MANGA]) {
      id
      title { romaji english native }
      format
      description(asHtml: false)
      coverImage { extraLarge }
      genres
      startDate { year month day }
      staff {
        edges {
          role
          node { name { native full } }
        }
      }
    }
  }
}
"""


class AniListProvider(BaseProvider):
    name = "anilist"

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        data = await self.post_json(
            GRAPHQL_URL,
            json={
                "query": SEARCH_QUERY,
                "variables": {"search": query, "perPage": limit},
            },
        )
        if not data:
            return []

        try:
            media = data["data"]["Page"]["media"] or []
        except (KeyError, TypeError):
            return []

        matches: list[dict[str, Any]] = []
        for item in media:
            match = self._parse(item)
            if match:
                matches.append(match)
        return matches

    def _parse(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = pick_title(
            {
                "romaji": item.get("title", {}).get("romaji"),
                "english": item.get("title", {}).get("english"),
                "native": item.get("title", {}).get("native"),
            },
            self.config.prefer_romaji,
        )
        if not title:
            return None

        raw: dict[str, Any] = {
            "title": title,
            "description": item.get("description"),
            "cover": (item.get("coverImage") or {}).get("extraLarge"),
            "genres": item.get("genres") or [],
        }

        start_date = item.get("startDate") or {}
        if start_date.get("year"):
            raw["publishedYear"] = start_date["year"]

        # Authors: staff edges whose role indicates a writing role.
        authors: list[str] = []
        for edge in (item.get("staff") or {}).get("edges") or []:
            role = (edge.get("role") or "").lower()
            if "story" in role or "author" in role or "original" in role:
                node = edge.get("node") or {}
                name = node.get("name") or {}
                full = name.get("full") or name.get("native")
                if full and full not in authors:
                    authors.append(full)
        if authors:
            raw["author"] = ", ".join(authors)

        return normalize_match(raw)
