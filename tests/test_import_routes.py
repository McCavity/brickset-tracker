"""Smoke tests for the three Brickset import routes."""
from fastapi.testclient import TestClient
from main import app


def test_import_page_renders(db):
    client = TestClient(app)
    r = client.get("/import/brickset")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The fetch button must be on the page so the user can start
    assert 'id="fetch-button"' in r.text
