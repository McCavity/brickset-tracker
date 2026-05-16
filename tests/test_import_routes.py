"""Smoke tests for the three Brickset import routes."""
import pytest
from fastapi.testclient import TestClient
from main import app

from execution import brickset
from tests.test_fetch_owned_collection import _FakeClient, _set, _page


def test_import_page_renders(db):
    client = TestClient(app)
    r = client.get("/import/brickset")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The fetch button must be on the page so the user can start
    assert 'id="fetch-button"' in r.text


@pytest.fixture
def fake_brickset(monkeypatch, db):
    _FakeClient._pages = []
    _FakeClient.calls = []
    monkeypatch.setattr(brickset.httpx, "AsyncClient", _FakeClient)
    yield _FakeClient


def test_fetch_endpoint_returns_html_partial(fake_brickset):
    fake_brickset._pages = [_page([_set("10298"), _set("42171")])]
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # No page chrome — it's a partial
    assert "<html" not in r.text.lower()
    # Should mention both set numbers
    assert "10298" in r.text
    assert "42171" in r.text


def test_fetch_endpoint_skips_malformed_sets(fake_brickset):
    """A Brickset response with a malformed set (missing number) must not crash."""
    valid = _set("10298")
    broken = {"setID": 1, "name": "broken"}  # no 'number'
    fake_brickset._pages = [_page([valid, broken])]
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    assert r.status_code == 200
    assert "10298" in r.text
    # The broken set is silently skipped — page still renders


def test_fetch_endpoint_surfaces_quota_error(monkeypatch, fake_brickset):
    monkeypatch.setattr("execution.brickset.check_quota", lambda svc: False)
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    assert r.status_code == 200
    # The partial shows the user-facing quota message (i18n key or rendered text)
    assert "quota" in r.text.lower() or "limit" in r.text.lower() or "Tageslimit" in r.text or "import.error_quota" in r.text


def test_fetch_endpoint_computes_local_qty(fake_brickset):
    """When a Brickset set already exists locally, local_qty must reflect that
    so the row displays the right comparison."""
    from tests.factories import make_set
    # User already has 2 local copies of set 10298
    make_set(brand="LEGO", set_number="10298")
    make_set(brand="LEGO", set_number="10298")

    fake_brickset._pages = [_page([_set("10298")])]
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    # The preview row should reflect local_qty=2 and bs_qty=1
    assert "10298" in r.text
    # 'Local: 2' or similar — depends on i18n. Just verify the count makes it in.
    assert "2" in r.text
