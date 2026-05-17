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
