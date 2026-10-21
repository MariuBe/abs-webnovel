"""Parser tests for each provider, using captured API fixtures.

These exercise the synchronous ``_parse`` methods directly (no network), so
they verify the mapping from each upstream shape to the ABS match shape.
"""

from __future__ import annotations

import json

from aiolimiter import AsyncLimiter

from abs_webnovel.config import Config
from abs_webnovel.providers.anilist import AniListProvider
from abs_webnovel.providers.mangadex import MangaDexProvider
from abs_webnovel.providers.novelbuddy import NovelBuddyProvider, _extract_items
from abs_webnovel.providers.ranobedb import RanobeDBProvider
from abs_webnovel.providers.webnovel import WebnovelProvider, _extract_json


def _provider(cls, **config_overrides):
    config = Config(**config_overrides)
    return cls(config, session=None, limiter=AsyncLimiter(1, 1))


# --- AniList ----------------------------------------------------------------


def test_anilist_parse_title_prefers_english(anilist_data):
    p = _provider(AniListProvider)
    media = anilist_data["data"]["Page"]["media"]
    match = p._parse(media[0])
    assert match is not None
    assert match["title"] == "Solo Leveling"
    assert match["publishedYear"] == 2018
    assert "Action" in match["genres"]
    assert match["cover"].startswith("https://s4.anilist.co/")


def test_anilist_parse_authors_from_staff(anilist_data):
    p = _provider(AniListProvider)
    media = anilist_data["data"]["Page"]["media"]
    match = p._parse(media[0])
    # "Original Story" / "Story" roles should be picked up as authors.
    assert "Chu-Gong" in match["author"]
    assert "So-Ryeong Gi" in match["author"]
    # Lettering / art roles should NOT be treated as authors.
    assert "Abigail Blackman" not in match["author"]


def test_anilist_parse_no_title_returns_none():
    p = _provider(AniListProvider)
    assert (
        p._parse({"title": {"romaji": None, "english": None, "native": None}}) is None
    )


# --- MangaDex ---------------------------------------------------------------


def test_mangadex_parse_title_from_alt_titles(mangadex_data):
    p = _provider(MangaDexProvider)
    item = mangadex_data["data"][0]
    match = p._parse(item)
    assert match is not None
    assert match["title"] == "Solo Leveling: Ragnarok"
    assert match["publishedYear"] == 2024
    assert "Action" in match["genres"]
    # Format tags (Long Strip, Full Color) must not leak into genres.
    assert "Long Strip" not in match["genres"]
    assert "Full Color" not in match["genres"]


def test_mangadex_parse_author_and_cover(mangadex_data):
    p = _provider(MangaDexProvider)
    item = mangadex_data["data"][0]
    match = p._parse(item)
    assert match["author"] == "DAUL (다울)"
    assert match["cover"].startswith("https://uploads.mangadex.org/covers/")
    assert match["cover"].endswith(".250.jpg")


def test_mangadex_parse_no_title_returns_none():
    p = _provider(MangaDexProvider)
    assert p._parse({"id": "x", "attributes": {"title": {}, "altTitles": []}}) is None


# --- RanobeDB ---------------------------------------------------------------


def test_ranobedb_parse_uses_detail(ranobedb_search, ranobedb_detail):
    p = _provider(RanobeDBProvider)
    book = ranobedb_search["books"][0]
    match = p._parse(book, ranobedb_detail["book"])
    assert match is not None
    assert match["title"].startswith("Demon Ruler 2")
    assert match["publishedYear"] == 2018
    assert match["author"] == "Ichiesa Kasane"
    assert match["publisher"] == "KADOKAWA"
    assert match["isbn"] == "9784040724119"
    assert match["cover"].startswith("https://images.ranobedb.org/")


def test_ranobedb_parse_series(ranobedb_search, ranobedb_detail):
    p = _provider(RanobeDBProvider)
    book = ranobedb_search["books"][0]
    match = p._parse(book, ranobedb_detail["book"])
    # The book belongs to the "Demon Ruler" series (different from its own title).
    assert match["series"] == [{"series": "Demon Ruler"}]


def test_ranobedb_parse_falls_back_to_search_book(ranobedb_search):
    p = _provider(RanobeDBProvider)
    book = ranobedb_search["books"][0]
    match = p._parse(book, {})
    assert match is not None
    assert match["title"].startswith("Demon Ruler 2")
    assert match["publishedYear"] == 2018


# --- Webnovel ---------------------------------------------------------------


def test_webnovel_parse_maps_fields(webnovel_data):
    p = _provider(WebnovelProvider)
    item = webnovel_data["data"]["bookInfo"]["bookItems"][0]
    match = p._parse(item)
    assert match is not None
    assert match["title"] == "The Legendary Mechanic"
    assert match["author"] == "齐佩甲"
    assert match["description"].startswith("In the future")
    assert match["cover"] == (
        "https://book-pic.webnovel.com/bookcover/1234567"
        "?imageMogr2/thumbnail/600x"
    )
    assert match["genres"] == ["EASTERN"]
    assert match["tags"] == ["Sci-Fi", "Action"]


def test_webnovel_parse_empty_tag_info(webnovel_data):
    p = _provider(WebnovelProvider)
    item = webnovel_data["data"]["bookInfo"]["bookItems"][1]
    match = p._parse(item)
    assert match is not None
    assert match["title"] == "Solo Max-Level Newbie"
    assert "tags" not in match


def test_webnovel_parse_no_title_returns_none():
    p = _provider(WebnovelProvider)
    assert p._parse({"bookId": "1", "authorName": "x"}) is None


def test_webnovel_extract_json_strips_pre_wrapper(webnovel_data):
    body = "<html><body><pre>" + json.dumps(webnovel_data) + "</pre></body></html>"
    data = _extract_json(body)
    assert data is not None
    assert data["code"] == 0


def test_webnovel_extract_json_plain_json(webnovel_data):
    data = _extract_json(json.dumps(webnovel_data))
    assert data is not None
    assert data["code"] == 0


def test_webnovel_extract_json_garbage_returns_none():
    assert _extract_json("<html><body>not json</body></html>") is None


# --- NovelBuddy -------------------------------------------------------------


def test_novelbuddy_parse_uses_detail(novelbuddy_data, novelbuddy_detail):
    p = _provider(NovelBuddyProvider)
    item = novelbuddy_data["data"]["items"][0]
    match = p._parse(item, novelbuddy_detail["data"]["title"])
    assert match is not None
    assert match["title"] == "Merchant Crab"
    assert match["author"] == "H0st"
    assert match["description"].startswith("A merchant crab")
    assert match["cover"] == "https://rs.novelbuddy.me/covers/merchant-crab.png"
    assert match["genres"] == ["Comedy", "Adventure"]
    assert match["tags"] == ["isecai", "sea"]
    # release_date is null; year comes from first_chapter_updated_at
    assert match["publishedYear"] == 2025


def test_novelbuddy_parse_falls_back_to_search_item(novelbuddy_data):
    p = _provider(NovelBuddyProvider)
    item = novelbuddy_data["data"]["items"][0]
    match = p._parse(item, {})
    assert match is not None
    assert match["title"] == "Merchant Crab"
    assert "author" not in match
    assert match["cover"] == "https://rs.novelbuddy.me/covers/merchant-crab.png"
    assert match["genres"] == ["Comedy", "Adventure"]


def test_novelbuddy_parse_empty_cover_and_authors(novelbuddy_data):
    p = _provider(NovelBuddyProvider)
    item = novelbuddy_data["data"]["items"][1]
    match = p._parse(item, {})
    assert match is not None
    assert match["title"] == "Merchant of the Seas"
    assert "cover" not in match
    assert "author" not in match


def test_novelbuddy_parse_no_title_returns_none():
    p = _provider(NovelBuddyProvider)
    assert p._parse({"id": "x", "slug": "x"}, {}) is None


def test_novelbuddy_extract_items_envelope(novelbuddy_data):
    items = _extract_items(novelbuddy_data)
    assert len(items) == 2
    assert items[0]["name"] == "Merchant Crab"


def test_novelbuddy_extract_items_top_level_list():
    items = _extract_items({"items": [{"name": "A"}, {"name": "B"}]})
    assert [i["name"] for i in items] == ["A", "B"]


def test_novelbuddy_extract_items_empty():
    assert _extract_items({}) == []
    assert _extract_items({"data": {}}) == []
