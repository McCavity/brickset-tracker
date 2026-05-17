"""Read/write brand → slug mappings (used by the merlinssteine.de URL builder)."""
from execution.db import get_connection


def brand_to_slug(brand: str) -> str:
    """Return the URL slug for a brand. Falls back to a sanitised version
    of the brand name if no mapping exists."""
    key = brand.lower().strip()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT slug FROM brand_slugs WHERE brand = ?", (key,)
        ).fetchone()
    if row:
        return row["slug"]
    return key.replace(" ", "-")


def list_brand_slugs() -> list[dict]:
    """Return all brand slug pairs, ordered by brand name."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT brand, slug FROM brand_slugs ORDER BY brand"
        ).fetchall()
    return [dict(r) for r in rows]


def add_brand_slug(brand: str, slug: str) -> None:
    """Insert a new brand → slug pair. Raises sqlite3.IntegrityError on duplicate."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO brand_slugs (brand, slug) VALUES (?, ?)",
            (brand.lower().strip(), slug.lower().strip()),
        )


def ensure_brand_slug(brand: str, slug: str) -> None:
    """Insert a brand → slug pair if not already present. Idempotent."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO brand_slugs (brand, slug) VALUES (?, ?)",
            (brand.lower().strip(), slug.lower().strip()),
        )


def update_brand_slug(brand: str, slug: str) -> None:
    """Update the slug for an existing brand. No-op if the brand doesn't exist."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE brand_slugs SET slug = ?, updated_at = datetime('now') WHERE brand = ?",
            (slug.lower().strip(), brand.lower().strip()),
        )


def delete_brand_slug(brand: str) -> None:
    """Remove a brand → slug pair. No-op if it doesn't exist."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM brand_slugs WHERE brand = ?",
            (brand.lower().strip(),),
        )
