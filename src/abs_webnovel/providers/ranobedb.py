"""RanobeDB provider (ranobedb.org).

The search endpoint returns only minimal fields, so for each hit we fetch the
book detail endpoint to get description, staff, publishers, series and ISBN.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import BaseProvider, normalize_match, pick_title

logger = logging.getLogger(__name__)

API_BASE = "https://ranobedb.org/api/v0"
IMAGE_BASE = "https://images.ranobedb.org"


class RanobeDBProvider(BaseProvider):
    name = "ranobedb"

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        data = await self.get_json(
            f"{API_BASE}/books",
            params={"q": query, "limit": limit},
        )
        if not data:
            return []

        books = data.get("books") or []
        matches: list[dict[str, Any]] = []
        for book in books:
            book_id = book.get("id")
            detail = await self.get_json(f"{API_BASE}/book/{book_id}")
            detail_book = (detail or {}).get("book") or {}
            match = self._parse(book, detail_book)
            if match:
                matches.append(match)
        return matches

    def _parse(
        self, search_book: dict[str, Any], detail: dict[str, Any]
    ) -> dict[str, Any] | None:
        book = detail or search_book

        title = pick_title(
            {
                "romaji": book.get("romaji"),
                "native": book.get("title"),
            },
            self.config.prefer_romaji,
        )
        if not title:
            return None

        raw: dict[str, Any] = {"title": title}

        description = book.get("description") or book.get("description_ja")
        if description:
            raw["description"] = description

        image = book.get("image") or {}
        if image.get("filename"):
            raw["cover"] = f"{IMAGE_BASE}/{image['filename']}"

        release_date = book.get("c_release_date")
        if release_date:
            try:
                raw["publishedYear"] = int(str(release_date)[:4])
            except ValueError:
                pass

        # Authors from the first edition's staff.
        authors: list[str] = []
        for edition in book.get("editions") or []:
            for staff in edition.get("staff") or []:
                if staff.get("role_type") == "author":
                    name = staff.get("romaji") or staff.get("name")
                    if name and name not in authors:
                        authors.append(name)
        if authors:
            raw["author"] = ", ".join(authors)

        publishers = [
            p.get("romaji") or p.get("name")
            for p in book.get("publishers") or []
            if p.get("publisher_type") == "publisher"
        ]
        publishers = [p for p in publishers if p]
        if publishers:
            raw["publisher"] = publishers[0]

        series = book.get("series") or {}
        series_title = pick_title(
            {"romaji": series.get("romaji"), "native": series.get("title")},
            self.config.prefer_romaji,
        )
        if series_title and series_title.lower() != title.lower():
            raw["series"] = [{"series": series_title}]

        # ISBN from the first release that has one.
        for release in book.get("releases") or []:
            if release.get("isbn13"):
                raw["isbn"] = str(release["isbn13"])
                break

        return normalize_match(raw)
