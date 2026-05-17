"""The sets table has a list_price column after init_db runs."""
from execution.db import get_connection


def _columns(conn) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(sets)").fetchall()}


def test_list_price_column_exists(db):
    """db fixture calls init_db on a fresh temp DB."""
    with get_connection() as conn:
        cols = _columns(conn)
    assert "list_price" in cols


def test_list_price_column_is_nullable(db):
    """Existing rows without list_price stay NULL. Verify by inserting
    without the column and reading it back."""
    from tests.factories import make_set
    set_id = make_set(brand="LEGO", set_number="42171", name="X", part_count=100)
    with get_connection() as conn:
        row = conn.execute("SELECT list_price FROM sets WHERE id=?", (set_id,)).fetchone()
    assert row["list_price"] is None


def test_alter_table_is_idempotent(db):
    """Running init_db twice on the same DB must not error."""
    from execution.db import init_db
    init_db()  # second call
    init_db()  # third call for good measure
    # If no exception, the migration is properly idempotent.
