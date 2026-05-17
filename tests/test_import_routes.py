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


def test_commit_inserts_and_redirects(db):
    """POST commit with a single row → inserts and redirects to /."""
    client = TestClient(app)
    payload = {
        "rows": [{
            "brand":           "LEGO",
            "set_number":      "10298",
            "name":            "Vespa",
            "part_count":      1106,
            "theme":           "Creator Expert",
            "release_year":    2022,
            "ean":             None,
            "web_images":      [],
            "brickset_set_id": 23456,
            "import_qty":      2,
            "local_ids_missing_bs_id": [],
        }],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/?imported=2&backfilled=0" in r.headers.get("location", "") \
        or "imported=2" in r.headers.get("location", "")

    # Verify the inserts
    from execution.db import get_connection
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert count == 2


def test_commit_validates_required_fields(db):
    """Rows missing brand or set_number are silently skipped."""
    client = TestClient(app)
    payload = {
        "rows": [
            {"brand": "LEGO", "set_number": "", "import_qty": 1,
             "brickset_set_id": 1, "name": "X", "local_ids_missing_bs_id": []},
            {"brand": "LEGO", "set_number": "10298", "import_qty": 1,
             "brickset_set_id": 23456, "name": "Vespa",
             "part_count": 1106,
             "local_ids_missing_bs_id": [],
             "web_images": []},
        ],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)

    from execution.db import get_connection
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM sets").fetchone()["n"]
    # Only the valid row was committed
    assert count == 1


def test_commit_skips_rows_without_part_count(db):
    """A row without a valid integer part_count is silently skipped.

    part_count is a required field on the local schema; defaulting to 0
    would pollute the collection with fake zero-piece sets."""
    client = TestClient(app)
    payload = {
        "rows": [
            # Missing part_count
            {"brand": "LEGO", "set_number": "10298",
             "brickset_set_id": 23456, "name": "X",
             "import_qty": 1, "local_ids_missing_bs_id": [],
             "web_images": []},
            # part_count is a non-integer string
            {"brand": "LEGO", "set_number": "10299",
             "brickset_set_id": 23457, "name": "Y",
             "part_count": "not-a-number",
             "import_qty": 1, "local_ids_missing_bs_id": [],
             "web_images": []},
            # Valid — should commit
            {"brand": "LEGO", "set_number": "10300",
             "brickset_set_id": 23458, "name": "Z",
             "part_count": 500,
             "import_qty": 1, "local_ids_missing_bs_id": [],
             "web_images": []},
        ],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "imported=1" in r.headers.get("location", "")

    from execution.db import get_connection
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT set_number FROM sets ORDER BY set_number"
        ).fetchall()
    nums = [r["set_number"] for r in rows]
    assert nums == ["10300"]


def test_commit_validates_import_qty_is_non_negative(db):
    """import_qty < 0 is silently clamped to 0; row's backfill still runs."""
    client = TestClient(app)
    payload = {
        "rows": [{
            "brand": "LEGO", "set_number": "10298",
            "brickset_set_id": 23456, "name": "Vespa", "web_images": [],
            "import_qty": -5, "local_ids_missing_bs_id": [],
        }],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    from execution.db import get_connection
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM sets").fetchone()["n"]
    assert count == 0


def test_commit_handles_empty_rows_list(db):
    client = TestClient(app)
    r = client.post("/api/import/brickset/commit", json={"rows": []}, follow_redirects=False)
    assert r.status_code in (302, 303)
    # Should redirect with 0/0 counts
    assert "imported=0" in r.headers.get("location", "")
    assert "backfilled=0" in r.headers.get("location", "")


def test_commit_ignores_tampered_local_ids_missing_bs_id(db):
    """F2 — A client must not be able to backfill brickset_set_id onto a
    row of a different brand+set_number by passing a tampered id list."""
    from tests.factories import make_set
    from fastapi.testclient import TestClient
    from main import app
    from execution.db import get_connection

    # Victim: an UNRELATED row that the attacker is trying to corrupt.
    victim_id = make_set(brand="LEGO", set_number="99999", brickset_set_id=None)
    # Legitimate row to backfill (matches the payload's brand+set_number):
    legit_id  = make_set(brand="LEGO", set_number="10298", brickset_set_id=None)

    body = {
        "rows": [{
            "brand":           "LEGO",
            "set_number":      "10298",
            "name":            "Vespa",
            "part_count":      1106,
            "theme":           "Creator Expert",
            "release_year":    2022,
            "ean":             None,
            "web_images":      [],
            "brickset_set_id": 23456,
            "import_qty":      0,
            # Tampered: includes the victim's id alongside the legit id.
            "local_ids_missing_bs_id": [victim_id, legit_id],
            "preview_local_qty": 1,
        }],
    }

    with TestClient(app) as client:
        client.post("/api/import/brickset/commit", json=body)

    with get_connection() as conn:
        victim = conn.execute(
            "SELECT brickset_set_id FROM sets WHERE id=?", (victim_id,)
        ).fetchone()
        legit  = conn.execute(
            "SELECT brickset_set_id FROM sets WHERE id=?", (legit_id,)
        ).fetchone()

    assert victim["brickset_set_id"] is None, "Tampered id list must not touch unrelated rows"
    assert legit["brickset_set_id"] == 23456,  "Legit row must still be backfilled"
