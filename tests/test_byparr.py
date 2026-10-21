"""Tests for the Byparr anti-bot proxy integration.

Byparr is a FlareSolverr-compatible service: ``POST /v1`` with
``{"cmd": "request.get", "url": ...}`` returns the rendered HTML of a page
after solving the Cloudflare challenge. These tests verify that
``BaseProvider.fetch_via_byparr`` parses that contract and that the
NovelUpdates provider routes through it when configured.
"""

from __future__ import annotations

import json
from typing import Any, Self

from aiolimiter import AsyncLimiter

from abs_webnovel.config import Config
from abs_webnovel.providers.novelupdates import NovelUpdatesProvider
from abs_webnovel.providers.webnovel import WebnovelProvider


class _FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeSession:
    """Minimal stand-in for aiohttp.ClientSession recording POST calls."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def post(self, url: str, *, json: dict[str, Any] | None = None, **_: Any):
        self.calls.append((url, json))
        return self.responses.pop(0)


def _byparr_ok(html: str) -> _FakeResponse:
    return _FakeResponse(
        200,
        {
            "status": "ok",
            "message": "Success",
            "solution": {
                "url": "https://www.novelupdates.com/",
                "status": 200,
                "cookies": [],
                "userAgent": "byparr-ua",
                "response": html,
                "contentType": "text/html",
            },
        },
    )


def _provider(config: Config, session: _FakeSession) -> NovelUpdatesProvider:
    return NovelUpdatesProvider(config, session=session, limiter=AsyncLimiter(10, 1))


# --- fetch_via_byparr -------------------------------------------------------


async def test_fetch_via_byparr_returns_html():
    session = _FakeSession([_byparr_ok("<html>ok</html>")])
    p = _provider(Config(byparr_url="http://byparr:8191"), session)
    html = await p.fetch_via_byparr("https://www.novelupdates.com/?s=x")
    assert html == "<html>ok</html>"
    # The request must target the /v1 endpoint with a FlareSolverr-style body.
    url, payload = session.calls[0]
    assert url == "http://byparr:8191/v1"
    assert payload == {
        "cmd": "request.get",
        "url": "https://www.novelupdates.com/?s=x",
        "maxTimeout": 60,
    }


async def test_fetch_via_byparr_disabled_returns_none():
    session = _FakeSession([])
    p = _provider(Config(byparr_url=""), session)
    assert await p.fetch_via_byparr("https://example.com") is None
    assert session.calls == []  # no HTTP call when not configured


async def test_fetch_via_byparr_error_status_returns_none():
    session = _FakeSession(
        [_FakeResponse(200, {"status": "error", "message": "Invalid request"})]
    )
    p = _provider(Config(byparr_url="http://byparr:8191"), session)
    assert await p.fetch_via_byparr("https://example.com") is None


async def test_fetch_via_byparr_challenge_not_solved_returns_none():
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                {
                    "status": "ok",
                    "solution": {"url": "https://example.com", "status": 403},
                },
            )
        ]
    )
    p = _provider(Config(byparr_url="http://byparr:8191"), session)
    assert await p.fetch_via_byparr("https://example.com") is None


# --- NovelUpdates routing ---------------------------------------------------


async def test_novelupdates_uses_byparr_when_configured():
    html = (
        '<a href="https://www.novelupdates.com/series/solo-leveling/" '
        'class="series-title">Solo Leveling</a>'
    )
    session = _FakeSession([_byparr_ok(html)])
    p = _provider(Config(byparr_url="http://byparr:8191"), session)
    matches = await p.search("solo leveling")
    assert [m["title"] for m in matches] == ["Solo Leveling"]
    # The search URL (with query params) was sent to Byparr.
    url, _ = session.calls[0]
    assert url == "http://byparr:8191/v1"


async def test_novelupdates_byparr_failure_returns_empty():
    session = _FakeSession(
        [_FakeResponse(200, {"status": "error", "message": "boom"})]
    )
    p = _provider(Config(byparr_url="http://byparr:8191"), session)
    # When Byparr is configured but fails, we do NOT fall back to a direct
    # request (it would just hit Cloudflare again) — we return no results.
    assert await p.search("solo leveling") == []


async def test_novelupdates_direct_fallback_when_no_byparr():
    # No Byparr configured: the provider falls back to a direct GET.
    class _DirectSession:
        def __init__(self) -> None:
            self.get_called = False

        def get(self, url: str, *, params: Any = None, headers: Any = None):
            self.get_called = True
            return _DirectResponse()

    class _DirectResponse:
        status = 200

        async def text(self) -> str:
            return (
                '<a href="https://www.novelupdates.com/series/solo-leveling/" '
                'class="series-title">Solo Leveling</a>'
            )

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    session = _DirectSession()
    p = _provider(Config(byparr_url=""), session)
    matches = await p.search("solo leveling")
    assert session.get_called is True
    assert [m["title"] for m in matches] == ["Solo Leveling"]


# --- Webnovel routing -------------------------------------------------------


def _webnovel_json() -> str:
    return json.dumps(
        {
            "code": 0,
            "data": {
                "bookInfo": {
                    "total": 1,
                    "isLast": 1,
                    "bookItems": [
                        {
                            "bookId": "1234567",
                            "bookName": "The Legendary Mechanic",
                            "authorName": "齐佩甲",
                            "categoryName": "EASTERN",
                            "tagInfo": ["Sci-Fi"],
                        }
                    ],
                }
            },
        }
    )


def _webnovel_provider(config: Config, session: _FakeSession) -> WebnovelProvider:
    return WebnovelProvider(config, session=session, limiter=AsyncLimiter(10, 1))


async def test_webnovel_uses_byparr_when_configured():
    # Byparr renders the JSON as plaintext HTML wrapped in <pre>.
    body = "<html><body><pre>" + _webnovel_json() + "</pre></body></html>"
    session = _FakeSession([_byparr_ok(body)])
    p = _webnovel_provider(Config(byparr_url="http://byparr:8191"), session)
    matches = await p.search("legendary mechanic")
    assert [m["title"] for m in matches] == ["The Legendary Mechanic"]
    # The search URL (with query params) was sent to Byparr's /v1 endpoint.
    url, payload = session.calls[0]
    assert url == "http://byparr:8191/v1"
    assert payload["cmd"] == "request.get"
    assert "keywords=legendary+mechanic" in payload["url"]
    assert "type=novel" in payload["url"]


async def test_webnovel_disabled_without_byparr():
    # No Byparr configured: the source is disabled (direct = Cloudflare 403).
    p = _webnovel_provider(Config(byparr_url=""), _FakeSession([]))
    assert p.enabled is False
    assert await p.search("legendary mechanic") == []


async def test_webnovel_byparr_failure_returns_empty():
    session = _FakeSession(
        [_FakeResponse(200, {"status": "error", "message": "boom"})]
    )
    p = _webnovel_provider(Config(byparr_url="http://byparr:8191"), session)
    assert await p.search("legendary mechanic") == []
