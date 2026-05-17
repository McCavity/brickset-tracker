"""Verifies the test DB fixture isolates each test."""
from execution.db import get_connection


def test_db_fixture_starts_empty(db):
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    assert count == 0


def test_db_fixture_can_insert(db):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO sets (brand, set_number, name, part_count, status) "
            "VALUES ('LEGO', '42171', 'McLaren P1', 3893, 'complete')"
        )
        count = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    assert count == 1


def test_db_fixture_is_isolated_between_tests(db):
    """Previous test inserted a row; this one should still start empty."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    assert count == 0


from tests.factories import make_set


def test_factory_inserts_set(db):
    set_id = make_set(brand="BlueBrixx", name="Castle", part_count=500)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT brand, name, part_count FROM sets WHERE id = ?", (set_id,)
        ).fetchone()
    assert row["brand"] == "BlueBrixx"
    assert row["name"] == "Castle"
    assert row["part_count"] == 500


def test_factory_accepts_list_price(db):
    """list_price added in Iteration 3.7; factory backfilled to accept it."""
    set_id = make_set(brand="LEGO", set_number="42171", name="McLaren", part_count=3893,
                      list_price=449.99)
    with get_connection() as conn:
        row = conn.execute("SELECT list_price FROM sets WHERE id = ?", (set_id,)).fetchone()
    assert row["list_price"] == 449.99
