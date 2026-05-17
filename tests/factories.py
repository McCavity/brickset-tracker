"""Helpers for building test data in the sets table."""
from execution.db import get_connection


def make_set(
    *,
    brand: str = "LEGO",
    set_number: str = "0000",
    name: str = "Test Set",
    part_count: int = 100,
    condition: str | None = None,
    location: str | None = None,
    date_of_purchase: str | None = "2025-01-01",
    note: str | None = None,
    theme: str | None = None,
    release_year: int | None = None,
    minifigs: int | None = None,
    price_paid: float | None = None,
    list_price: float | None = None,
    ean: str | None = None,
    status: str = "complete",
) -> int:
    """Insert a set row and return its id."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO sets
               (brand, set_number, name, part_count, condition, location,
                date_of_purchase, note, theme, release_year, minifigs,
                price_paid, list_price, ean, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (brand, set_number, name, part_count, condition, location,
             date_of_purchase, note, theme, release_year, minifigs,
             price_paid, list_price, ean, status),
        )
        return cur.lastrowid
