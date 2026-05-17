"""
Orchestrates add, edit, and delete operations on set records.
See architecture/SOP-001-add-set-workflow.md and SOP-008-database.md.
"""
import json
import logging
import shutil
from datetime import date

log = logging.getLogger(__name__)

from execution.db import get_connection
from execution.photos import finalise_photos

REQUIRED = ("brand", "set_number", "name", "part_count")

SORT_ALLOWLIST = {
    "date_of_purchase", "name", "brand", "part_count", "price_paid", "created_at"
}

CONDITION_VALUES = ("ovp", "im_bau", "gebaut", "abgebaut", "verkauft")


def save_set(data: dict, session_id: str | None = None) -> dict:
    """
    Validate, determine completeness, check duplicates, and persist a set record.
    Returns {id, status, duplicates: list}.
    """
    # Determine completeness
    missing = [f for f in REQUIRED if not data.get(f)]
    status = "draft" if missing else "complete"

    # Default purchase date for complete records
    if status == "complete" and not data.get("date_of_purchase"):
        data["date_of_purchase"] = date.today().isoformat()

    # Check duplicates
    duplicates = _find_duplicates(data.get("brand", ""), data.get("set_number", ""))

    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO sets
               (ean, brand, set_number, name, part_count, condition, location,
                date_of_purchase, note, theme, release_year, web_images, own_photos,
                minifigs, price_paid, list_price, brickset_set_id, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data.get("ean"),
                data.get("brand", ""),
                data.get("set_number", ""),
                data.get("name", ""),
                _int(data.get("part_count")),
                data.get("condition"),
                data.get("location"),
                data.get("date_of_purchase"),
                data.get("note"),
                data.get("theme"),
                _int(data.get("release_year")),
                json.dumps(data.get("web_images") or []),
                json.dumps(data.get("own_photos") or []),
                _int(data.get("minifigs")),
                _float(data.get("price_paid")),
                _float(data.get("list_price")),
                _int(data.get("brickset_set_id")),
                status,
            ),
        )
        set_id = cursor.lastrowid

    # Move staged photos if any
    if session_id and set_id:
        own_photos = finalise_photos(session_id, set_id)
        if own_photos:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE sets SET own_photos=?, updated_at=datetime('now') WHERE id=?",
                    (json.dumps(own_photos), set_id),
                )

    return {"id": set_id, "status": status, "duplicates": duplicates, "missing": missing}


def get_sets(
    sort_by: str = "date_of_purchase",
    sort_dir: str = "DESC",
    q: str | None = None,
    brands: list[str] | None = None,
    conditions: list[str] | None = None,
    themes: list[str] | None = None,
    statuses: list[str] | None = None,
) -> list[dict]:
    """Return all set records matching the given filters.

    q: case-insensitive substring match across text-ish fields.
    brands/conditions/themes/statuses: OR within each list, AND across lists.
    Empty list or None means no filter on that dimension.
    """
    if sort_by not in SORT_ALLOWLIST:
        sort_by = "date_of_purchase"
    sort_dir = "ASC" if sort_dir.upper() == "ASC" else "DESC"

    where_clauses, params = _build_filter_clauses(
        q=q, brands=brands, conditions=conditions,
        themes=themes, statuses=statuses,
    )
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT id, ean, brand, set_number, name, part_count, condition,
                       location, date_of_purchase, note, theme, release_year,
                       web_images, own_photos, minifigs, price_paid, list_price,
                       brickset_set_id, status, created_at
                FROM sets
                {where_sql}
                ORDER BY {sort_by} {sort_dir}, id DESC""",
            params,
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


def count_all_sets() -> int:
    """Total set count across the whole collection, ignoring all filters."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sets").fetchone()
    return row["n"]


def get_facet_counts(
    q: str | None = None,
    brands: list[str] | None = None,
    conditions: list[str] | None = None,
    themes: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """Return {"brand": {"LEGO": 12, ...}, "condition": {...}, ...}.

    Each facet's counts are computed ignoring that facet's own filter
    but honouring all other filters and the search query. This lets the
    UI show selectable alternatives even within an active facet.
    NULL values are excluded — "no theme" isn't a useful facet option.
    """
    facet_definitions = [
        ("brand",     {"brands": None,     "conditions": conditions, "themes": themes, "statuses": statuses}),
        ("condition", {"brands": brands,   "conditions": None,       "themes": themes, "statuses": statuses}),
        ("theme",     {"brands": brands,   "conditions": conditions, "themes": None,   "statuses": statuses}),
        ("status",    {"brands": brands,   "conditions": conditions, "themes": themes, "statuses": None}),
    ]

    results: dict[str, dict[str, int]] = {}

    with get_connection() as conn:
        for column, filter_overrides in facet_definitions:
            where_clauses, params = _build_filter_clauses(q=q, **filter_overrides)
            where_sql = ("WHERE " + " AND ".join(where_clauses) + f" AND {column} IS NOT NULL"
                         if where_clauses
                         else f"WHERE {column} IS NOT NULL")
            rows = conn.execute(
                f"""SELECT {column} AS value, COUNT(*) AS n
                    FROM sets
                    {where_sql}
                    GROUP BY {column}""",
                params,
            ).fetchall()
            results[column] = {r["value"]: r["n"] for r in rows}

    return results


def _build_filter_clauses(
    *,
    q: str | None = None,
    brands: list[str] | None = None,
    conditions: list[str] | None = None,
    themes: list[str] | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[str], list]:
    """Build the WHERE-clause fragments and parameter list for a filtered query."""
    where_clauses: list[str] = []
    params: list = []

    if q:
        searchable_columns = [
            "name", "brand", "set_number", "ean", "theme", "note",
            "location", "condition",
            "CAST(release_year AS TEXT)", "CAST(part_count AS TEXT)",
        ]
        wrapped = [f"py_lower({col}) LIKE py_lower(?)" for col in searchable_columns]
        where_clauses.append("(" + " OR ".join(wrapped) + ")")
        params.extend([f"%{q}%"] * len(searchable_columns))

    for column, values in (
        ("brand", brands),
        ("condition", conditions),
        ("theme", themes),
        ("status", statuses),
    ):
        if values:
            placeholders = ",".join("?" * len(values))
            where_clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)

    return where_clauses, params


def delete_set(set_id: int) -> None:
    """Delete a set record and its uploads/{id}/ photo folder.
    Caller must have confirmed with user first.
    """
    # NOTE: lazy import so tests can monkeypatch execution.photos.UPLOADS_ROOT.
    from execution.photos import UPLOADS_ROOT
    with get_connection() as conn:
        conn.execute("DELETE FROM sets WHERE id=?", (set_id,))
    shutil.rmtree(UPLOADS_ROOT / str(set_id), ignore_errors=True)


def get_set(set_id: int) -> dict | None:
    """Fetch a single set by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sets WHERE id=?", (set_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_set(set_id: int, data: dict, session_id: str | None = None) -> dict:
    """Update an existing set record. Keeps existing own_photos unless removed.
    Removed photos are unlinked from disk after the DB UPDATE succeeds (S2)."""
    missing = [f for f in REQUIRED if not data.get(f)]
    status = "draft" if missing else "complete"

    kept_photos = json.loads(data.get("existing_own_photos") or "[]")

    # Compute which photos the user removed BEFORE issuing the UPDATE,
    # so we have a stable diff against the DB's pre-update state.
    with get_connection() as conn:
        old_row = conn.execute(
            "SELECT own_photos FROM sets WHERE id=?", (set_id,)
        ).fetchone()
    old_photos = json.loads(old_row["own_photos"] or "[]") if old_row else []
    removed = set(old_photos) - set(kept_photos)

    with get_connection() as conn:
        conn.execute(
            """UPDATE sets SET
               ean=?, brand=?, set_number=?, name=?, part_count=?, condition=?,
               location=?, date_of_purchase=?, note=?, theme=?, release_year=?,
               web_images=?, own_photos=?, minifigs=?, price_paid=?, list_price=?,
               brickset_set_id=?, status=?, updated_at=datetime('now')
               WHERE id=?""",
            (
                data.get("ean"),
                data.get("brand", ""),
                data.get("set_number", ""),
                data.get("name", ""),
                _int(data.get("part_count")),
                data.get("condition"),
                data.get("location"),
                data.get("date_of_purchase"),
                data.get("note"),
                data.get("theme"),
                _int(data.get("release_year")),
                json.dumps(data.get("web_images") or []),
                json.dumps(kept_photos),
                _int(data.get("minifigs")),
                _float(data.get("price_paid")),
                _float(data.get("list_price")),
                _int(data.get("brickset_set_id")),
                status,
                set_id,
            ),
        )

    # S2 — unlink the removed photos AFTER the DB UPDATE succeeds, so a
    # failed UPDATE leaves files in place (orphaned) rather than gone with
    # stale DB references. This matches S1's "DB first, filesystem second"
    # ordering for the delete path.
    # NOTE: lazy import so tests can monkeypatch execution.photos.UPLOADS_ROOT.
    from execution.photos import UPLOADS_ROOT
    for rel in removed:
        try:
            # Paths in own_photos are relative to project root (e.g. "uploads/12/foo.jpg").
            # Strip the leading "uploads/" so we can resolve against UPLOADS_ROOT
            # (which itself ends in /uploads) without doubling the segment.
            stripped = rel[len("uploads/"):] if rel.startswith("uploads/") else rel
            (UPLOADS_ROOT / stripped).unlink(missing_ok=True)
        except OSError as exc:
            # Don't block the user's edit on a filesystem oddity (perms, race, etc.).
            log.warning("Could not unlink %s during edit cleanup: %s", rel, exc)

    if session_id:
        new_photos = finalise_photos(session_id, set_id)
        if new_photos:
            all_photos = kept_photos + new_photos
            with get_connection() as conn:
                conn.execute(
                    "UPDATE sets SET own_photos=?, updated_at=datetime('now') WHERE id=?",
                    (json.dumps(all_photos), set_id),
                )

    return {"id": set_id, "status": status, "missing": missing}


def get_brands() -> list[str]:
    """Return distinct brand names already stored in the collection."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT brand FROM sets WHERE brand != '' ORDER BY brand"
        ).fetchall()
    return [r["brand"] for r in rows]


def count_owned(brand: str, set_number: str) -> int:
    """Count complete records with this brand+set_number (for Brickset qtyOwned)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as n FROM sets WHERE brand=? AND set_number=? AND status='complete'",
            (brand, set_number),
        ).fetchone()
    return row["n"] if row else 0


def find_local_rows_missing_brickset_id(brand: str, set_number: str) -> list[int]:
    """Return ids of local rows matching brand+set_number that lack a brickset_set_id.

    Used by the Brickset import to backfill the id on existing rows that were
    entered before Brickset had the set indexed.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM sets WHERE brand=? AND set_number=? AND brickset_set_id IS NULL",
            (brand, set_number),
        ).fetchall()
    return [r["id"] for r in rows]


def commit_import_rows(rows: list[dict]) -> dict:
    """Persist a batch of Brickset import rows — idempotent under retries.

    Each row dict has:
      brand, set_number, name, part_count, theme, release_year, ean,
      web_images (list of str), brickset_set_id (int),
      import_qty (int >= 0), local_ids_missing_bs_id (list[int]),
      preview_local_qty (int, optional — defaults to 0).

    For each row:
      - UPDATEs brickset_set_id on every id in local_ids_missing_bs_id.
      - Inserts at most `import_qty` new rows, minus any rows the user
        already added (by another tab, retry, etc.) since the preview
        snapshot was taken. The current local count is read inside the
        same transaction immediately before inserting (F3).

    Returns {"created": N, "backfilled": K} — total rows created/updated.
    """
    today = date.today().isoformat()
    note = f"Imported from Brickset on {today}"
    created = 0
    backfilled = 0

    with get_connection() as conn:
        for row in rows:
            brand      = row["brand"]
            set_number = row["set_number"]
            existing_ids = row.get("local_ids_missing_bs_id") or []
            if existing_ids:
                placeholders = ",".join("?" * len(existing_ids))
                cur = conn.execute(
                    f"""UPDATE sets SET brickset_set_id = ?, updated_at = datetime('now')
                        WHERE id IN ({placeholders})""",
                    (row["brickset_set_id"], *existing_ids),
                )
                backfilled += cur.rowcount

            # F3 — idempotent insert: cap at the remaining desired count.
            import_qty        = int(row.get("import_qty") or 0)
            preview_local_qty = int(row.get("preview_local_qty") or 0)
            current_local_count = conn.execute(
                "SELECT COUNT(*) AS n FROM sets "
                "WHERE brand=? AND set_number=? AND status='complete'",
                (brand, set_number),
            ).fetchone()["n"]
            delta_already_imported = max(0, current_local_count - preview_local_qty)
            actual_insert = max(0, import_qty - delta_already_imported)

            for _ in range(actual_insert):
                conn.execute(
                    """INSERT INTO sets
                       (brand, set_number, name, part_count, theme, release_year,
                        ean, web_images, brickset_set_id, status, note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?)""",
                    (
                        brand, set_number, row["name"],
                        row.get("part_count"), row.get("theme"),
                        row.get("release_year"), row.get("ean"),
                        json.dumps(row.get("web_images") or []),
                        row["brickset_set_id"], note,
                    ),
                )
                created += 1

    return {"created": created, "backfilled": backfilled}


def _find_duplicates(brand: str, set_number: str) -> list[dict]:
    if not brand or not set_number:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, condition, note, date_of_purchase, status
               FROM sets WHERE brand=? AND set_number=?
               ORDER BY date_of_purchase DESC""",
            (brand, set_number),
        ).fetchall()
    return [dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row)
    for field in ("web_images", "own_photos"):
        try:
            d[field] = json.loads(d.get(field) or "[]")
        except (ValueError, TypeError):
            d[field] = []
    return d


def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def _float(v) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None
