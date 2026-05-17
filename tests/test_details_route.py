"""GET /sets/{id} — details view route."""
from fastapi.testclient import TestClient
from main import app
from tests.factories import make_set


def test_details_page_renders_existing_set(db):
    set_id = make_set(brand="LEGO", set_number="42171", name="McLaren P1", part_count=3893)
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The page must surface the set's identity
    assert "McLaren P1" in r.text
    assert "42171" in r.text
    assert "LEGO" in r.text


def test_details_page_redirects_for_missing_id(db):
    client = TestClient(app)
    r = client.get("/sets/9999", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/"
