"""End-to-end test of the /search endpoint (providers stubbed, no network)."""

from __future__ import annotations

from typing import Any

import pytest

from abs_webnovel.config import Config
from abs_webnovel.main import create_app


class FakeProvider:
    def __init__(self, name: str, results: list[dict[str, Any]]):
        self.name = name
        self._results = results

    @property
    def enabled(self) -> bool:
        return True

    async def search(self, query, author=None, limit=None):
        return self._results


def _fake_build(cfg, session, limiter):
    return [
        FakeProvider("anilist", [{"title": "Solo Leveling", "author": "A"}]),
        FakeProvider(
            "mangadex",
            [
                {"title": "Solo Leveling", "author": "B"},
                {"title": "Omniscient Reader"},
            ],
        ),
    ]


@pytest.fixture
async def client(aiohttp_client):
    app = create_app(Config(), build_providers=_fake_build)
    return await aiohttp_client(app)


async def test_search_returns_abs_shape(client):
    resp = await client.get("/search", params={"mediaType": "book", "query": "solo"})
    assert resp.status == 200
    data = await resp.json()
    assert "matches" in data
    assert isinstance(data["matches"], list)
    # Deduped by title, ordered by source priority.
    assert [m["title"] for m in data["matches"]] == [
        "Solo Leveling",
        "Omniscient Reader",
    ]
    assert data["matches"][0]["author"] == "A"


async def test_search_empty_query(client):
    resp = await client.get("/search", params={"mediaType": "book", "query": ""})
    assert resp.status == 200
    assert await resp.json() == {"matches": []}


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"
    assert data["sources"] == ["anilist", "mangadex"]
