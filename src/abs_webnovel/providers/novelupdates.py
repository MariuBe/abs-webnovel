"""NovelUpdates provider (www.novelupdates.com).

The site sits behind Cloudflare and frequently returns 403 to non-browser
clients. Two strategies, in order:

1. If a Byparr anti-bot proxy is configured (``BYPARR_URL``), the search page
   is fetched through it — Byparr drives a real browser, solves the challenge,
   and returns the rendered HTML.
2. Otherwise a direct request is attempted with a browser-like User-Agent.

When both fail (or no proxy is set), this source returns no results and the
other providers carry the request.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

from ..base import BaseProvider, normalize_match

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.novelupdates.com/"

# A realistic browser UA; Cloudflare still blocks most datacenter clients.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Series rows look like:
# <a href="https://www.novelupdates.com/series/slug/" class="series-title">Title</a>
_SERIES_LINK_RE = re.compile(
    r'<a[^>]+href="https://www\.novelupdates\.com/series/[^"]+"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


class NovelUpdatesProvider(BaseProvider):
    name = "novelupdates"

    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        limit = limit or self.config.search_limit
        search_url = f"{SEARCH_URL}?{urlencode({'s': query, 'post_type': 'series'})}"

        # Preferred path: route through Byparr, which solves the Cloudflare
        # challenge and returns the rendered HTML.
        html_text = await self.fetch_via_byparr(search_url)

        # Fallback: direct request with a browser-like User-Agent.
        if html_text is None and not self.config.byparr_url:
            async with self.limiter:
                try:
                    async with self.session.get(
                        SEARCH_URL,
                        params={"s": query, "post_type": "series"},
                        headers=_HEADERS,
                    ) as resp:
                        if resp.status != 200:
                            logger.debug(
                                "novelupdates: search -> %s (likely Cloudflare)",
                                resp.status,
                            )
                            return []
                        html_text = await resp.text()
                except Exception as exc:  # noqa: BLE001 - provider must not raise
                    logger.debug("novelupdates: search failed: %s", exc)
                    return []

        if not html_text:
            return []

        titles = _SERIES_LINK_RE.findall(html_text)
        # Dedupe, keep order.
        seen: set[str] = set()
        unique: list[str] = []
        for title in titles:
            title = title.strip()
            if title and title.lower() not in seen:
                seen.add(title.lower())
                unique.append(title)

        matches = [normalize_match({"title": t}) for t in unique[:limit]]
        return [m for m in matches if m]
