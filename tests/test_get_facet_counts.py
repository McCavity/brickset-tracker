"""get_facet_counts returns the distinct values + counts for each
facet (brand, condition, theme, status), respecting the current search
and all OTHER facet filters but NOT the facet's own filter.

This is what lets a user click "LEGO" in the brand facet and still
see "BlueBrixx (3)" so they can switch."""
from navigation.set_manager import get_facet_counts
from tests.factories import make_set


def test_facet_counts_unfiltered(db):
    make_set(brand="LEGO", condition="ovp", theme="Star Wars", set_number="1")
    make_set(brand="LEGO", condition="gebaut", theme="City", set_number="2")
    make_set(brand="BlueBrixx", condition="ovp", theme="Castle", set_number="3")

    facets = get_facet_counts()

    assert facets["brand"] == {"LEGO": 2, "BlueBrixx": 1}
    assert facets["condition"] == {"ovp": 2, "gebaut": 1}
    assert facets["theme"] == {"Star Wars": 1, "City": 1, "Castle": 1}
    assert facets["status"] == {"complete": 3}


def test_facet_counts_respects_search(db):
    make_set(brand="LEGO", name="Star Wars X-Wing", set_number="1")
    make_set(brand="LEGO", name="City Police", set_number="2")
    make_set(brand="BlueBrixx", name="Star Wars Replica", set_number="3")

    facets = get_facet_counts(q="star wars")
    assert facets["brand"] == {"LEGO": 1, "BlueBrixx": 1}


def test_brand_facet_ignores_brand_filter(db):
    """When the user has ticked 'LEGO' in the brand facet, the brand facet
    itself must still show BlueBrixx so they can switch. Other facets
    DO honour the brand filter."""
    make_set(brand="LEGO", condition="ovp", set_number="1")
    make_set(brand="LEGO", condition="gebaut", set_number="2")
    make_set(brand="BlueBrixx", condition="ovp", set_number="3")
    make_set(brand="BlueBrixx", condition="ovp", set_number="4")

    facets = get_facet_counts(brands=["LEGO"])

    # brand facet ignores its own filter — shows everyone
    assert facets["brand"] == {"LEGO": 2, "BlueBrixx": 2}
    # condition facet respects the brand filter — only LEGO conditions
    assert facets["condition"] == {"ovp": 1, "gebaut": 1}


def test_condition_facet_ignores_condition_filter(db):
    make_set(brand="LEGO", condition="ovp", set_number="1")
    make_set(brand="LEGO", condition="gebaut", set_number="2")
    make_set(brand="BlueBrixx", condition="ovp", set_number="3")

    facets = get_facet_counts(conditions=["ovp"])

    # condition facet ignores its own filter
    assert facets["condition"] == {"ovp": 2, "gebaut": 1}
    # brand facet respects the condition filter — only ovp brands
    assert facets["brand"] == {"LEGO": 1, "BlueBrixx": 1}


def test_facet_excludes_null_values(db):
    make_set(brand="LEGO", theme=None, set_number="1")
    make_set(brand="LEGO", theme="City", set_number="2")
    make_set(brand="BlueBrixx", theme=None, set_number="3")

    facets = get_facet_counts()

    # NULL theme is not surfaced as a facet option
    assert facets["theme"] == {"City": 1}
    # brand still counts every row
    assert facets["brand"] == {"LEGO": 2, "BlueBrixx": 1}


def test_facet_returns_empty_dict_when_no_rows(db):
    facets = get_facet_counts()
    assert facets == {"brand": {}, "condition": {}, "theme": {}, "status": {}}
