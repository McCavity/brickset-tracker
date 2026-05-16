"""GET /api/sets/filter returns an HTML partial (no full page chrome)."""
from fastapi.testclient import TestClient

from main import app
from tests.factories import make_set


def test_partial_returns_200_html(db):
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_partial_has_no_html_chrome(db):
    """The partial should NOT include <html>, <head>, or <body> tags."""
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    body = r.text.lower()
    assert "<html" not in body
    assert "<head" not in body
    assert "<body" not in body


def test_partial_contains_results_region(db):
    make_set(name="Apple", set_number="1")
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    assert 'id="results-region"' in r.text
    assert "Apple" in r.text


def test_partial_honours_search(db):
    make_set(name="Apple", set_number="1")
    make_set(name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/api/sets/filter?q=apple")
    assert "Apple" in r.text
    assert "Banana" not in r.text


def test_partial_honours_brand_filter(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="BlueBrixx", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/api/sets/filter?brand=LEGO")
    assert "Apple" in r.text
    assert "Banana" not in r.text
