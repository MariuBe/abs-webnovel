"""Tests for merge_results (configurable priority merge)."""

from abs_webnovel.providers import merge_results


def _m(title: str, **extra) -> dict:
    return {"title": title, **extra}


def test_priority_mode_interleaves_by_source_priority():
    results = [
        ("anilist", [_m("A1"), _m("A2")]),
        ("mangadex", [_m("M1"), _m("M2")]),
        ("ranobedb", [_m("R1")]),
    ]
    merged = merge_results(results, mode="priority", limit=5)
    # Round-robin: one result from each source per round, in priority order.
    assert [m["title"] for m in merged] == ["A1", "M1", "R1", "A2", "M2"]


def test_priority_mode_top_result_from_highest_priority():
    results = [
        ("anilist", [_m("From AniList")]),
        ("mangadex", [_m("From MangaDex")]),
    ]
    merged = merge_results(results, mode="priority", limit=5)
    assert merged[0]["title"] == "From AniList"


def test_priority_mode_dedupes_by_normalized_title():
    results = [
        ("anilist", [_m("Solo Leveling")]),
        ("mangadex", [_m("solo  leveling!"), _m("Omniscient Reader")]),
    ]
    merged = merge_results(results, mode="priority", limit=5)
    assert [m["title"] for m in merged] == ["Solo Leveling", "Omniscient Reader"]


def test_priority_mode_keeps_first_occurrence():
    results = [
        ("anilist", [_m("Solo Leveling", author="A")]),
        ("mangadex", [_m("Solo Leveling", author="B")]),
    ]
    merged = merge_results(results, mode="priority", limit=5)
    assert len(merged) == 1
    assert merged[0]["author"] == "A"


def test_priority_mode_respects_limit():
    results = [
        ("anilist", [_m(f"Book {i}") for i in range(10)]),
    ]
    merged = merge_results(results, mode="priority", limit=3)
    assert len(merged) == 3


def test_first_mode_returns_first_nonempty_source():
    results = [
        ("anilist", []),
        ("mangadex", [_m("Solo Leveling"), _m("Omniscient Reader")]),
        ("ranobedb", [_m("Demon Ruler")]),
    ]
    merged = merge_results(results, mode="first", limit=5)
    assert [m["title"] for m in merged] == ["Solo Leveling", "Omniscient Reader"]


def test_first_mode_respects_limit():
    results = [("anilist", [_m(f"Book {i}") for i in range(10)])]
    merged = merge_results(results, mode="first", limit=2)
    assert len(merged) == 2


def test_first_mode_all_empty():
    assert merge_results([("anilist", []), ("mangadex", [])], "first", 5) == []


def test_priority_mode_all_empty():
    assert merge_results([("anilist", []), ("mangadex", [])], "priority", 5) == []
