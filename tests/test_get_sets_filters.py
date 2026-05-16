"""get_sets() supports brand/condition/theme/status list filters.
Within a facet: OR. Across facets: AND."""
from navigation.set_manager import get_sets
from tests.factories import make_set


def test_brand_filter_single(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(brands=["LEGO"])
    assert len(results) == 1
    assert results[0]["brand"] == "LEGO"


def test_brand_filter_multiple_is_or(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    make_set(brand="Cobi", name="C", set_number="3")
    results = get_sets(brands=["LEGO", "Cobi"])
    assert {r["brand"] for r in results} == {"LEGO", "Cobi"}


def test_condition_filter(db):
    make_set(condition="ovp", name="A", set_number="1")
    make_set(condition="gebaut", name="B", set_number="2")
    results = get_sets(conditions=["gebaut"])
    assert len(results) == 1
    assert results[0]["condition"] == "gebaut"


def test_theme_filter(db):
    make_set(theme="Star Wars", name="A", set_number="1")
    make_set(theme="City", name="B", set_number="2")
    results = get_sets(themes=["Star Wars"])
    assert len(results) == 1


def test_status_filter(db):
    make_set(status="complete", name="A", set_number="1")
    make_set(status="draft", name="B", set_number="2")
    results = get_sets(statuses=["draft"])
    assert len(results) == 1
    assert results[0]["status"] == "draft"


def test_facets_combine_as_and(db):
    # Only one row matches both brand=LEGO AND condition=gebaut
    make_set(brand="LEGO", condition="gebaut", name="A", set_number="1")
    make_set(brand="LEGO", condition="ovp", name="B", set_number="2")
    make_set(brand="BlueBrixx", condition="gebaut", name="C", set_number="3")
    results = get_sets(brands=["LEGO"], conditions=["gebaut"])
    assert len(results) == 1
    assert results[0]["name"] == "A"


def test_search_and_filters_combine(db):
    make_set(brand="LEGO", name="Star Wars X-Wing", set_number="1")
    make_set(brand="LEGO", name="City Police", set_number="2")
    make_set(brand="BlueBrixx", name="Star Wars Replica", set_number="3")
    results = get_sets(q="star wars", brands=["LEGO"])
    assert len(results) == 1
    assert results[0]["set_number"] == "1"


def test_empty_filter_list_means_no_filter(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(brands=[])
    assert len(results) == 2


def test_none_filter_means_no_filter(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(brands=None)
    assert len(results) == 2
