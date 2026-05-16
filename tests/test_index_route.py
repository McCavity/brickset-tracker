"""GET / accepts search and filter query params and feeds them through
to get_sets / get_facet_counts. Smoke-level — verifies the route wires
the params through, not the underlying SQL behaviour (that's covered
in Phase 1)."""
from fastapi.testclient import TestClient

from main import app
from tests.factories import make_set


def test_index_renders_empty_collection(db):
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    # Empty collection: no <div class="set-card"> elements
    assert 'class="set-card"' not in r.text


def test_index_renders_all_sets_by_default(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="LEGO", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Apple" in r.text
    assert "Banana" in r.text


def test_index_q_param_narrows_results(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="LEGO", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/?q=apple")
    assert "Apple" in r.text
    assert "Banana" not in r.text


def test_index_brand_param_filters(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="BlueBrixx", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/?brand=LEGO")
    assert "Apple" in r.text
    assert "Banana" not in r.text


def test_index_brand_param_is_repeatable(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="BlueBrixx", name="Banana", set_number="2")
    make_set(brand="Cobi", name="Cherry", set_number="3")
    client = TestClient(app)
    r = client.get("/?brand=LEGO&brand=BlueBrixx")
    assert "Apple" in r.text
    assert "Banana" in r.text
    assert "Cherry" not in r.text


def test_index_combines_search_and_filter(db):
    make_set(brand="LEGO", name="Star Wars X-Wing", set_number="1")
    make_set(brand="LEGO", name="City Police", set_number="2")
    make_set(brand="BlueBrixx", name="Star Wars Replica", set_number="3")
    client = TestClient(app)
    r = client.get("/?q=star+wars&brand=LEGO")
    assert "X-Wing" in r.text
    assert "City Police" not in r.text
    assert "Replica" not in r.text
