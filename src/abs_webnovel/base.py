"""Base provider interface and shared helpers.

Every upstream source implements :class:`BaseProvider` and returns a list of
normalized match dicts that conform to the Audiobookshelf
``CustomProviderAdapter`` contract (see README.md).
"""

from __future__ import annotations

import html
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import aiohttp
from aiolimiter import AsyncLimiter

from .config import Config

logger = logging.getLogger(__name__)

# Keys the ABS CustomProviderAdapter understands. Anything else is dropped.
_MATCH_KEYS = {
    "title",
    "subtitle",
    "author",
    "narrator",
    "publisher",
    "publishedYear",
    "cover",
    "isbn",
    "asin",
    "language",
    "description",
    "genres",
    "tags",
    "series",
    "duration",
}

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str | None) -> str | None:
    """Strip HTML tags and unescape entities from a description."""
    if not value:
        return None
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def pick_title(titles: dict[str, Any], prefer_romaji: bool = True) -> str | None:
    """Pick the best title from a mapping of language/variant -> title.

    Preference order: english > romaji > native > first available. English is
    preferred over romaji because it is the official global title (e.g.
    "Solo Leveling" rather than the Korean romanization "Na Honjaman Level Up").
    """
    if not titles:
        return None
    if prefer_romaji:
        for key in ("english", "en", "romaji"):
            value = titles.get(key)
            if value:
                return str(value)
    for key in ("native", "ja", "ko", "zh"):
        value = titles.get(key)
        if value:
            return str(value)
    for value in titles.values():
        if value:
            return str(value)
    return None


def language_name(tag: str | None) -> str | None:
    """Human-readable language name from a BCP-47 tag (e.g. 'ja' -> 'Japanese')."""
    if not tag:
        return None
    try:
        import langcodes

        return langcodes.Language.get(tag).display_name()
    except Exception:  # noqa: BLE001 - langcodes is best-effort
        return tag


def normalize_match(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Coerce a raw provider result into the ABS match shape.

    Returns ``None`` when the match has no usable title.
    """
    title = raw.get("title")
    if not title or not str(title).strip():
        return None

    match: dict[str, Any] = {"title": str(title).strip()}

    for key in (
        "subtitle",
        "author",
        "narrator",
        "publisher",
        "cover",
        "isbn",
        "asin",
        "language",
    ):
        value = raw.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            match[key] = value

    year = raw.get("publishedYear")
    if year is not None:
        try:
            match["publishedYear"] = int(year)
        except (TypeError, ValueError):
            pass

    description = strip_html(raw.get("description"))
    if description:
        match["description"] = description

    for key in ("genres", "tags"):
        value = raw.get(key)
        if isinstance(value, str):
            items = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, (list, tuple)):
            items = [str(v).strip() for v in value if str(v).strip()]
        else:
            items = []
        # Dedupe case-insensitively, keep first occurrence.
        seen: set[str] = set()
        deduped = []
        for item in items:
            lowered = item.lower()
            if lowered not in seen:
                seen.add(lowered)
                deduped.append(item)
        if deduped:
            match[key] = deduped

    series = raw.get("series")
    if isinstance(series, list):
        normalized_series = []
        for entry in series:
            if isinstance(entry, dict) and entry.get("series"):
                item: dict[str, Any] = {"series": str(entry["series"]).strip()}
                sequence = entry.get("sequence")
                if sequence is not None and str(sequence).strip():
                    item["sequence"] = sequence
                normalized_series.append(item)
        if normalized_series:
            match["series"] = normalized_series

    duration = raw.get("duration")
    if duration is not None:
        try:
            match["duration"] = float(duration)
        except (TypeError, ValueError):
            pass

    return {k: v for k, v in match.items() if k in _MATCH_KEYS}


class BaseProvider(ABC):
    """Common plumbing for all upstream sources."""

    #: Unique source name used in SOURCE_PRIORITY.
    name: str = "base"

    def __init__(
        self,
        config: Config,
        session: aiohttp.ClientSession,
        limiter: AsyncLimiter,
    ) -> None:
        self.config = config
        self.session = session
        self.limiter = limiter

    @property
    def enabled(self) -> bool:
        """Whether this source can be used with the current configuration."""
        return True

    @abstractmethod
    async def search(
        self, query: str, author: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Search the upstream source and return normalized matches.

        Implementations must swallow their own errors and return ``[]`` on
        failure so one broken source never breaks the whole request.
        """

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any | None:
        """GET a URL through the shared rate limiter. Returns parsed JSON or None."""
        async with self.limiter:
            try:
                async with self.session.get(
                    url, params=params, headers=headers
                ) as resp:
                    if resp.status != 200:
                        logger.debug("%s: GET %s -> %s", self.name, url, resp.status)
                        return None
                    return await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001 - provider must not raise
                logger.debug("%s: GET %s failed: %s", self.name, url, exc)
                return None

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any | None:
        """POST a JSON body through the shared rate limiter."""
        async with self.limiter:
            try:
                async with self.session.post(url, json=json, headers=headers) as resp:
                    if resp.status != 200:
                        logger.debug("%s: POST %s -> %s", self.name, url, resp.status)
                        return None
                    return await resp.json(content_type=None)
            except Exception as exc:  # noqa: BLE001 - provider must not raise
                logger.debug("%s: POST %s failed: %s", self.name, url, exc)
                return None

    async def fetch_via_byparr(
        self, url: str, *, max_timeout: int = 60
    ) -> str | None:
        """Fetch a page through the configured Byparr anti-bot proxy.

        Byparr is a FlareSolverr-compatible service: it drives a real browser,
        solves the Cloudflare/captcha challenge, and returns the fully rendered
        HTML in ``solution.response``. The ``cf_clearance`` cookie it obtains is
        bound to Byparr's own User-Agent and egress IP, so it cannot be reused
        by our own client — the request itself must go through Byparr.

        Returns the rendered HTML, or ``None`` when Byparr is not configured,
        the request fails, or the challenge could not be solved.
        """
        byparr = self.config.byparr_url
        if not byparr:
            return None
        payload = {"cmd": "request.get", "url": url, "maxTimeout": max_timeout}
        data = await self.post_json(f"{byparr}/v1", json=payload)
        if not isinstance(data, dict) or data.get("status") != "ok":
            logger.debug(
                "%s: byparr fetch failed for %s: %s",
                self.name,
                url,
                (data or {}).get("message", "no response"),
            )
            return None
        solution = data.get("solution") or {}
        if solution.get("status") != 200:
            logger.debug(
                "%s: byparr challenge not solved for %s (status %s)",
                self.name,
                url,
                solution.get("status"),
            )
            return None
        html_text = solution.get("response")
        return html_text or None
