"""Parser tests for each provider, using captured API fixtures.

These exercise the synchronous ``_parse`` methods directly (no network), so
they verify the mapping from each upstream shape to the ABS match shape.
"""

from __future__ import annotations

from aiolimiter import AsyncLimiter

from abs_webnovel.config import Config
from abs_webnovel.providers.anilist import AniListProvider
from abs_webnovel.providers.mangadex import MangaDexProvider
from abs_webnovel.providers.ranobedb import RanobeDBProvider


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
