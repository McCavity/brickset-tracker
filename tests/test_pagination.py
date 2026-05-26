"""Pagination on the list view + /api/sets/filter partial."""
from fastapi.testclient import TestClient

from main import app, ALLOWED_PAGE_SIZES, DEFAULT_PAGE_SIZE, _paginate
from tests.factories import make_set


# -----------------------------------------------------------------------------
#  Unit tests for the _paginate helper
# -----------------------------------------------------------------------------

def test_paginate_default_size():
    items = list(range(60))
    out = _paginate(items, page=1, size=25)
    assert out["sets"] == list(range(25))
    assert out["page"] == 1
    assert out["page_count"] == 3
    assert out["start"] == 0
    assert out["end"] == 25
    assert out["filtered_total"] == 60


def test_paginate_second_page():
    items = list(range(60))
    out = _paginate(items, page=2, size=25)
    assert out["sets"] == list(range(25, 50))
    assert out["page"] == 2
    assert out["start"] == 25
    assert out["end"] == 50


def test_paginate_last_page_partial():
    items = list(range(60))
    out = _paginate(items, page=3, size=25)
    assert out["sets"] == list(range(50, 60))
    assert out["start"] == 50
    assert out["end"] == 60


def test_paginate_size_all_returns_everything():
    items = list(range(60))
    out = _paginate(items, page=1, size=0)
    assert out["sets"] == items
    assert out["page"] == 1
    assert out["page_count"] == 1
    assert out["size"] == 0


def test_paginate_clamps_page_too_high():
    items = list(range(10))
    out = _paginate(items, page=99, size=25)
    # 10 items / 25 per page = 1 page total → page should be clamped to 1
    assert out["page"] == 1
    assert out["sets"] == items


def test_paginate_clamps_page_too_low():
    items = list(range(60))
    out = _paginate(items, page=0, size=25)
    assert out["page"] == 1


def test_paginate_unknown_size_falls_back_to_default():
    items = list(range(100))
    out = _paginate(items, page=1, size=7)   # 7 not in ALLOWED_PAGE_SIZES
    assert out["size"] == DEFAULT_PAGE_SIZE


def test_paginate_empty():
    out = _paginate([], page=1, size=25)
    assert out["sets"] == []
    assert out["page_count"] == 1
    assert out["filtered_total"] == 0


# -----------------------------------------------------------------------------
#  Integration tests against the partial endpoint
# -----------------------------------------------------------------------------

def test_partial_default_page_size(db):
    for i in range(30):
        make_set(name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    assert r.status_code == 200
    # Default size is 25 → set #29 should NOT be shown (page 1 covers 0..24)
    # All sets are sorted by date_of_purchase DESC (default). make_set probably
    # gives them all the same date, so order is undefined — we test counts only.
    assert 'data-page="1"' in r.text
    assert 'data-size="25"' in r.text
    assert 'data-page-count="2"' in r.text
    assert 'data-filtered-total="30"' in r.text


def test_partial_page_two(db):
    for i in range(30):
        make_set(name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/api/sets/filter?page=2&size=25")
    assert r.status_code == 200
    assert 'data-page="2"' in r.text


def test_partial_size_all(db):
    for i in range(30):
        make_set(name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/api/sets/filter?size=0")
    assert 'data-size="0"' in r.text
    assert 'data-page-count="1"' in r.text


def test_partial_pagination_nav_hidden_when_one_page(db):
    make_set(name="Solo", set_number="1")
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    # Only 1 set → no pagination-nav needed
    assert 'pagination-nav' not in r.text


def test_partial_pagination_nav_shown_when_multiple_pages(db):
    for i in range(30):
        make_set(name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/api/sets/filter?size=10")
    assert 'pagination-nav' in r.text


def test_partial_preserves_filters_in_pagination_links(db):
    for i in range(30):
        make_set(brand="LEGO", name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/api/sets/filter?brand=LEGO&size=10")
    # The "next page" link should carry the brand filter through
    assert "brand=LEGO" in r.text
    assert "size=10" in r.text


def test_index_default_pagination(db):
    for i in range(40):
        make_set(name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'data-page="1"' in r.text
    assert 'data-filtered-total="40"' in r.text
    assert 'data-page-count="2"' in r.text


def test_index_page_two(db):
    for i in range(40):
        make_set(name=f"Set {i:02d}", set_number=str(i))
    client = TestClient(app)
    r = client.get("/?page=2")
    assert r.status_code == 200
    assert 'data-page="2"' in r.text


def test_allowed_page_sizes_in_partial(db):
    make_set(name="One", set_number="1")
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    # All page-size options should appear in the size selector
    for opt in ALLOWED_PAGE_SIZES:
        if opt == 0:
            assert "size=0" in r.text   # "all" link
        else:
            assert f"size={opt}" in r.text
