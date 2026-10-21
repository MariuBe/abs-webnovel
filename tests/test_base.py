"""Tests for base helpers (normalize_match, pick_title, strip_html) and config."""

from abs_webnovel.base import normalize_match, pick_title, strip_html
from abs_webnovel.config import Config

# --- strip_html -------------------------------------------------------------


def test_strip_html_removes_tags_and_unescapes():
    assert strip_html("<p>Hello <b>world</b> &amp; co</p>") == "Hello world & co"


def test_strip_html_empty():
    assert strip_html(None) is None
    assert strip_html("   ") is None
    assert strip_html("<div></div>") is None


# --- pick_title -------------------------------------------------------------


def test_pick_title_prefers_english_over_romaji():
    assert (
        pick_title({"romaji": "Romaji", "english": "English", "native": "ネイティブ"})
        == "English"
    )


def test_pick_title_falls_back_to_romaji():
    assert pick_title({"romaji": "Romaji", "native": "ネイティブ"}) == "Romaji"


def test_pick_title_falls_back_to_native():
    assert pick_title({"native": "ネイティブ"}) == "ネイティブ"


def test_pick_title_no_romaji_prefers_english():
    assert pick_title({"english": "English", "native": "ネイティブ"}) == "English"


def test_pick_title_none():
    assert pick_title({}) is None
    assert pick_title({"romaji": None, "native": None}) is None


# --- normalize_match --------------------------------------------------------


def test_normalize_match_requires_title():
    assert normalize_match({"author": "X"}) is None
    assert normalize_match({"title": "  "}) is None


def test_normalize_match_drops_unknown_keys():
    match = normalize_match({"title": "T", "bogus": 1, "author": "A"})
    assert match == {"title": "T", "author": "A"}


def test_normalize_match_dedupes_genres_case_insensitive():
    match = normalize_match({"title": "T", "genres": ["Action", "action", "Fantasy"]})
    assert match["genres"] == ["Action", "Fantasy"]


def test_normalize_match_genres_from_comma_string():
    match = normalize_match({"title": "T", "genres": "Action, Fantasy, Action"})
    assert match["genres"] == ["Action", "Fantasy"]


def test_normalize_match_published_year_coerced():
    assert (
        normalize_match({"title": "T", "publishedYear": "2018"})["publishedYear"]
        == 2018
    )
    assert "publishedYear" not in normalize_match(
        {"title": "T", "publishedYear": "nope"}
    )


def test_normalize_match_series():
    match = normalize_match(
        {"title": "T", "series": [{"series": "Demon Ruler"}, {"series": ""}]}
    )
    assert match["series"] == [{"series": "Demon Ruler"}]


def test_normalize_match_description_sanitized():
    match = normalize_match({"title": "T", "description": "<p>Hi</p>"})
    assert match["description"] == "Hi"


# --- config -----------------------------------------------------------------


def test_config_from_env_defaults(monkeypatch):
    for var in (
        "HOST",
        "PORT",
        "LOG_LEVEL",
        "SEARCH_LIMIT",
        "SOURCE_PRIORITY",
        "MERGE_MODE",
        "PREFER_ROMAJI",
        "MAL_CLIENT_ID",
        "RATE_LIMIT",
        "RATE_PERIOD",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = Config.from_env()
    assert cfg.port == 8080
    assert cfg.search_limit == 5
    assert cfg.merge_mode == "priority"
    assert cfg.prefer_romaji is True
    assert cfg.source_priority == [
        "anilist",
        "mangadex",
        "ranobedb",
        "myanimelist",
        "novelupdates",
        "webnovel",
        "novelbuddy",
    ]


def test_config_from_env_custom(monkeypatch):
    monkeypatch.setenv("SOURCE_PRIORITY", "ranobedb, anilist, unknown")
    monkeypatch.setenv("MERGE_MODE", "first")
    monkeypatch.setenv("SEARCH_LIMIT", "10")
    monkeypatch.setenv("PREFER_ROMAJI", "false")
    monkeypatch.setenv("MAL_CLIENT_ID", "abc123")
    cfg = Config.from_env()
    assert cfg.source_priority == ["ranobedb", "anilist", "unknown"]
    assert cfg.merge_mode == "first"
    assert cfg.search_limit == 10
    assert cfg.prefer_romaji is False
    assert cfg.mal_client_id == "abc123"


def test_config_invalid_merge_mode_falls_back(monkeypatch):
    monkeypatch.setenv("MERGE_MODE", "bogus")
    assert Config.from_env().merge_mode == "priority"
