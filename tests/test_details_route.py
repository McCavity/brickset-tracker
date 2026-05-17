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


def test_details_page_renders_merlinssteine_link_always(db):
    """merlinssteine link is rendered for any brand, even when Brickset isn't applicable."""
    set_id = make_set(brand="BlueBrixx", set_number="103756", name="Castle", part_count=500)
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert "merlinssteine.de/sets/bb-103756" in r.text


def test_details_page_renders_brickset_link_only_when_id_set(db):
    """No brickset_set_id → no Brickset link."""
    set_id = make_set(brand="LEGO", set_number="00000", name="Unknown", part_count=1)
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert "brickset.com/sets/" not in r.text


def test_details_page_renders_brickset_link_when_id_set(db):
    """brickset_set_id present → Brickset link rendered."""
    from execution.db import get_connection
    set_id = make_set(brand="LEGO", set_number="42171", name="McLaren P1", part_count=3893)
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=48541 WHERE id=?", (set_id,))
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert "brickset.com/sets/42171-1/" in r.text


def test_details_page_renders_sync_button_only_for_lego_with_brickset_id(db):
    """Sync button visibility: LEGO + brickset_set_id."""
    from execution.db import get_connection
    # Case A: BlueBrixx with brickset_set_id (impossible in practice but test the guard)
    bx_id = make_set(brand="BlueBrixx", set_number="1", name="X", part_count=1)
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=1 WHERE id=?", (bx_id,))
    # Case B: LEGO without brickset_set_id
    lg_id = make_set(brand="LEGO", set_number="2", name="Y", part_count=1)
    # Case C: LEGO with brickset_set_id
    lg2_id = make_set(brand="LEGO", set_number="3", name="Z", part_count=1)
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=42 WHERE id=?", (lg2_id,))

    client = TestClient(app)
    # Case A: BlueBrixx + bs_id — sync NOT rendered (wrong brand)
    assert "syncBrickset(" + str(bx_id) + "," not in client.get(f"/sets/{bx_id}").text
    # Case B: LEGO without bs_id — sync NOT rendered (no id)
    assert "syncBrickset(" + str(lg_id) + "," not in client.get(f"/sets/{lg_id}").text
    # Case C: LEGO + bs_id — sync IS rendered
    assert "syncBrickset(" + str(lg2_id) + "," in client.get(f"/sets/{lg2_id}").text
