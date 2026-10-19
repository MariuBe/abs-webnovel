"""Shared fixtures: captured upstream API responses."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def anilist_data():
    return load("anilist_search.json")


@pytest.fixture
def mangadex_data():
    return load("mangadex_search.json")


@pytest.fixture
def ranobedb_search():
    return load("ranobedb_search.json")


@pytest.fixture
def ranobedb_detail():
    return load("ranobedb_detail.json")
