"""commit_import_rows performs two operations per row:
  1. Backfill brickset_set_id on existing local rows in local_ids_missing_bs_id.
  2. Insert import_qty new rows with the Brickset metadata.
Both are independent — a row can have import_qty=0 (just backfill) or empty
local_ids_missing_bs_id (just insert)."""
from execution.db import get_connection
from navigation.set_manager import commit_import_rows
from tests.factories import make_set


def _vespa_row(import_qty=1, local_ids_missing_bs_id=None):
    return {
        "brand":           "LEGO",
        "set_number":      "10298",
        "name":            "Vespa 125",
        "part_count":      1106,
        "theme":           "Creator Expert",
        "release_year":    2022,
        "ean":             "5702016912661",
        "web_images":      ["https://images.brickset.com/sets/large/10298-1.jpg"],
        "brickset_set_id": 23456,
        "import_qty":      import_qty,
        "local_ids_missing_bs_id": local_ids_missing_bs_id or [],
    }


def test_inserts_new_rows(db):
    result = commit_import_rows([_vespa_row(import_qty=3)])
    assert result["created"] == 3
    assert result["backfilled"] == 0
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchall()
    assert len(rows) == 3
    for row in rows:
        assert row["name"] == "Vespa 125"
        assert row["part_count"] == 1106
        assert row["theme"] == "Creator Expert"
        assert row["release_year"] == 2022
        assert row["ean"] == "5702016912661"
        assert row["brickset_set_id"] == 23456
        assert row["status"] == "complete"
        assert "Imported from Brickset" in (row["note"] or "")


def test_backfills_existing_rows(db):
    existing = make_set(brand="LEGO", set_number="10298")
    result = commit_import_rows([_vespa_row(
        import_qty=0,
        local_ids_missing_bs_id=[existing],
    )])
    assert result["created"] == 0
    assert result["backfilled"] == 1
    with get_connection() as conn:
        row = conn.execute("SELECT brickset_set_id FROM sets WHERE id=?", (existing,)).fetchone()
    assert row["brickset_set_id"] == 23456


def test_inserts_and_backfills_together(db):
    a = make_set(brand="LEGO", set_number="10298")
    b = make_set(brand="LEGO", set_number="10298")
    result = commit_import_rows([_vespa_row(
        import_qty=2,
        local_ids_missing_bs_id=[a, b],
    )])
    assert result["created"] == 2
    assert result["backfilled"] == 2
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert total == 4  # 2 existing + 2 newly inserted


def test_zero_qty_zero_backfill_is_noop(db):
    result = commit_import_rows([_vespa_row(import_qty=0)])
    assert result == {"created": 0, "backfilled": 0}


def test_multiple_rows_in_one_call(db):
    rows = [
        _vespa_row(import_qty=1),
        {
            "brand":           "LEGO",
            "set_number":      "42171",
            "name":            "McLaren P1",
            "part_count":      3893,
            "theme":           "Technic",
            "release_year":    2023,
            "ean":             None,
            "web_images":      [],
            "brickset_set_id": 48541,
            "import_qty":      2,
            "local_ids_missing_bs_id": [],
        },
    ]
    result = commit_import_rows(rows)
    assert result == {"created": 3, "backfilled": 0}


def test_image_url_stored_in_web_images_json(db):
    commit_import_rows([_vespa_row(import_qty=1)])
    with get_connection() as conn:
        row = conn.execute("SELECT web_images FROM sets WHERE set_number='10298'").fetchone()
    import json
    images = json.loads(row["web_images"])
    assert images == ["https://images.brickset.com/sets/large/10298-1.jpg"]
