"""Smoke tests for the settings/brand-slugs routes."""
from fastapi.testclient import TestClient
from main import app


def test_settings_page_renders(db):
    client = TestClient(app)
    r = client.get("/settings/brand-slugs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Seeded brands must be visible
    assert "lego" in r.text
    assert "pantasy" in r.text


def test_add_route_inserts_and_redirects(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/add",
                    data={"brand": "Ikea", "slug": "ikea-store"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"

    from execution.brand_slugs import brand_to_slug
    assert brand_to_slug("ikea") == "ikea-store"


def test_add_route_duplicate_returns_error_redirect(db):
    """Inserting a brand that already exists redirects with ?error=duplicate&brand=…"""
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/add",
                    data={"brand": "LEGO", "slug": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    loc = r.headers["location"]
    assert "error=duplicate" in loc
    assert "brand=lego" in loc.lower()


def test_add_route_empty_returns_error_redirect(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/add",
                    data={"brand": "  ", "slug": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "error=empty" in r.headers["location"]


def test_update_route_changes_slug(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/lego/update",
                    data={"slug": "lg"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"
    from execution.brand_slugs import brand_to_slug
    assert brand_to_slug("lego") == "lg"


def test_update_route_unknown_brand_redirects_silently(db):
    """No row exists → no-op + redirect to settings page."""
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/nonexistent/update",
                    data={"slug": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"


def test_update_route_empty_slug_returns_error_redirect(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/lego/update",
                    data={"slug": "  "},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "error=empty" in r.headers["location"]


def test_delete_route_removes_row_and_redirects(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/lego/delete",
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"
    from execution.brand_slugs import brand_to_slug
    assert brand_to_slug("lego") == "lego"  # falls back to default


def test_delete_route_unknown_brand_redirects_silently(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/nonexistent/delete",
                    follow_redirects=False)
    assert r.status_code in (302, 303)
