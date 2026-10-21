"""Webnovel provider (www.webnovel.com).

The whole site — including its JSON search API — sits behind Cloudflare and
returns 403 to plain HTTP clients, so every request is routed through the
configured Byparr anti-bot proxy. The source is disabled when no Byparr is
configured (a direct request would just hit Cloudflare again).

Byparr/Camoufox renders JSON responses as plaintext HTML, wrapping the body in
``<pre>...</pre>`` tags; the wrapper is stripped before parsing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlencode

from ..base import BaseProvider, normalize_match

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.webnovel.com/go/pcm/search/result"
COVER_BASE = "https://book-pic.webnovel.com/bookcover"

# Byparr renders JSON as plaintext HTML: <html>...<pre>{...}</pre></html>.
_PRE_RE = re.compile(r"<pre>(.*)</pre>", re.DOTALL)


class WebnovelProvider(BaseProvider):
    name = "webnovel"

    @property
    def enabled(self) -> bool:
        return bool(self.config.byparr_url)

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        search_url = f"{SEARCH_URL}?{urlencode({'keywords': query, 'pageIndex': 1, 'type': 'novel'})}"

        body = await self.fetch_via_byparr(search_url)
        if not body:
            return []

        data = _extract_json(body)
        if not data:
            return []

        book_info = (data.get("data") or {}).get("bookInfo") or {}
        items = book_info.get("bookItems") or []

        matches: list[dict[str, Any]] = []
        for item in items[:limit]:
            match = self._parse(item)
            if match:
                matches.append(match)
        return matches

    def _parse(self, item: dict[str, Any]) -> dict[str, Any] | None:
        title = item.get("bookName")
        if not title:
            return None

        raw: dict[str, Any] = {"title": title}

        author = item.get("authorName")
        if author:
            raw["author"] = author

        description = item.get("description")
        if description:
            raw["description"] = description

        book_id = item.get("bookId")
        if book_id:
            raw["cover"] = f"{COVER_BASE}/{book_id}?imageMogr2/thumbnail/600x"

        category = item.get("categoryName")
        if category:
            raw["genres"] = [category]

        tags = _clean_tags(item.get("tagInfo"))
        if tags:
            raw["tags"] = tags

        return normalize_match(raw)


def _clean_tags(tag_info: Any) -> list[str]:
    """Coerce Webnovel's ``tagInfo`` (list of strings or objects) to names."""
    if not isinstance(tag_info, list):
        return []
    tags: list[str] = []
    for tag in tag_info:
        if isinstance(tag, str):
            if tag.strip():
                tags.append(tag.strip())
        elif isinstance(tag, dict):
            name = tag.get("tagName") or tag.get("name")
            if name and str(name).strip():
                tags.append(str(name).strip())
    return tags


def _extract_json(body: str) -> dict[str, Any] | None:
    """Parse a Byparr-rendered JSON body, stripping the ``<pre>`` wrapper."""
    text = body
    m = _PRE_RE.search(body)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        logger.debug("webnovel: could not parse search response")
        return None
    return data if isinstance(data, dict) else None
