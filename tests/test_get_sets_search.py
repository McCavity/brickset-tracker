"""get_sets(q=...) does a case-insensitive substring match across all
text-ish fields: name, brand, set_number, ean, theme, note, location,
condition, release_year, part_count."""
from navigation.set_manager import get_sets
from tests.factories import make_set


def test_search_matches_name(db):
    make_set(name="Star Wars X-Wing", set_number="11111")
    make_set(name="City Police Station", set_number="22222")
    results = get_sets(q="x-wing")
    assert len(results) == 1
    assert results[0]["set_number"] == "11111"


def test_search_is_case_insensitive(db):
    make_set(name="Tower Bridge", set_number="10214")
    results = get_sets(q="TOWER")
    assert len(results) == 1


def test_search_matches_umlauts(db):
    make_set(name="Schöne Möbel", set_number="99999")
    results = get_sets(q="möbel")
    assert len(results) == 1


def test_search_matches_brand(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(q="bluebrixx")
    assert len(results) == 1
    assert results[0]["set_number"] == "2"


def test_search_matches_set_number(db):
    make_set(set_number="42171", name="A")
    make_set(set_number="10214", name="B")
    results = get_sets(q="42171")
    assert len(results) == 1


def test_search_matches_ean(db):
    make_set(ean="5702017595672", name="A", set_number="1")
    make_set(ean="4060904018514", name="B", set_number="2")
    results = get_sets(q="5702017")
    assert len(results) == 1


def test_search_matches_theme(db):
    make_set(theme="Star Wars", name="A", set_number="1")
    make_set(theme="City", name="B", set_number="2")
    results = get_sets(q="star wars")
    assert len(results) == 1


def test_search_matches_note(db):
    make_set(note="Birthday gift from Tim", name="A", set_number="1")
    make_set(note="", name="B", set_number="2")
    results = get_sets(q="tim")
    assert len(results) == 1


def test_search_matches_location(db):
    make_set(location="Living room shelf", name="A", set_number="1")
    make_set(location="Basement", name="B", set_number="2")
    results = get_sets(q="shelf")
    assert len(results) == 1


def test_search_matches_release_year(db):
    make_set(release_year=2024, name="A", set_number="1")
    make_set(release_year=1999, name="B", set_number="2")
    results = get_sets(q="2024")
    assert len(results) == 1


def test_search_matches_part_count(db):
    make_set(part_count=3893, name="A", set_number="1")
    make_set(part_count=42, name="B", set_number="2")
    results = get_sets(q="3893")
    assert len(results) == 1


def test_search_empty_string_returns_all(db):
    make_set(name="A", set_number="1")
    make_set(name="B", set_number="2")
    assert len(get_sets(q="")) == 2
    assert len(get_sets(q=None)) == 2


def test_search_no_match_returns_empty(db):
    make_set(name="A", set_number="1")
    results = get_sets(q="nonexistent")
    assert results == []
