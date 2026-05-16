"""find_local_rows_missing_brickset_id returns the ids of local rows that
match a brand+set_number AND have NULL brickset_set_id. These are the rows
the import will backfill."""
from navigation.set_manager import find_local_rows_missing_brickset_id
from tests.factories import make_set


def test_returns_empty_when_no_matching_rows(db):
    make_set(brand="LEGO", set_number="00000")
    assert find_local_rows_missing_brickset_id("LEGO", "99999") == []


def test_returns_ids_for_rows_with_null_brickset_id(db):
    a = make_set(brand="LEGO", set_number="42171")
    b = make_set(brand="LEGO", set_number="42171")
    ids = find_local_rows_missing_brickset_id("LEGO", "42171")
    assert sorted(ids) == sorted([a, b])


def test_excludes_rows_with_existing_brickset_id(db):
    a = make_set(brand="LEGO", set_number="42171")  # NULL bs_id
    b = make_set(brand="LEGO", set_number="42171")  # will get bs_id below
    from execution.db import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=99 WHERE id=?", (b,))
    ids = find_local_rows_missing_brickset_id("LEGO", "42171")
    assert ids == [a]


def test_brand_match_is_case_sensitive(db):
    # Existing get_sets is case-insensitive via py_lower; the BACKFILL helper
    # uses exact match because import always passes "LEGO" (Brickset is LEGO-only)
    make_set(brand="LEGO", set_number="42171")
    assert find_local_rows_missing_brickset_id("lego", "42171") == []
