"""brand_slugs table is created by init_db() and seeded from BRAND_SLUGS dict."""
from execution.db import get_connection


def _columns(conn, table) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_brand_slugs_table_exists(db):
    with get_connection() as conn:
        cols = _columns(conn, "brand_slugs")
    assert cols == {"brand", "slug", "created_at", "updated_at"}


def test_brand_slugs_seeded_from_dict(db):
    """All hardcoded BRAND_SLUGS entries are present after init_db()."""
    from execution.scraper import BRAND_SLUGS
    with get_connection() as conn:
        rows = conn.execute("SELECT brand, slug FROM brand_slugs").fetchall()
    db_pairs = {(r["brand"], r["slug"]) for r in rows}
    expected = {(b, s) for b, s in BRAND_SLUGS.items()}
    assert expected.issubset(db_pairs), f"missing seed entries: {expected - db_pairs}"


def test_brand_slugs_seed_does_not_overwrite_user_edits(db):
    """If a user has edited a seeded slug, re-running init_db() must not revert it."""
    from execution.db import init_db
    with get_connection() as conn:
        conn.execute("UPDATE brand_slugs SET slug = 'XXX' WHERE brand = 'lego'")
    init_db()  # second call
    with get_connection() as conn:
        row = conn.execute("SELECT slug FROM brand_slugs WHERE brand = 'lego'").fetchone()
    assert row["slug"] == "XXX", "user edit was overwritten by re-seeding!"


def test_brand_slugs_brand_is_primary_key(db):
    """Inserting a duplicate brand must raise IntegrityError."""
    import sqlite3
    from execution.db import get_connection
    with get_connection() as conn:
        try:
            conn.execute("INSERT INTO brand_slugs (brand, slug) VALUES ('lego', 'duplicate')")
            assert False, "duplicate insert should have raised IntegrityError"
        except sqlite3.IntegrityError:
            pass
