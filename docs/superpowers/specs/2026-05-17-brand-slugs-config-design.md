# Brand Slug Configuration — Design

**Status:** Approved 2026-05-17
**Project:** brickset-tracker
**Iteration:** 4.5

## Goal

Make the brand → merlinssteine.de URL-slug mapping user-configurable through the app, instead of requiring a code change every time a new brand appears (Lumibricks, Pantasy, etc.). A standalone settings page at `/settings/brand-slugs` lets the user add, edit, and delete mappings. The existing hardcoded `BRAND_SLUGS` dict in `execution/scraper.py` becomes seed data for fresh installs; runtime lookups read from a new SQLite table.

## URL + Navigation

- New routes:
  - `GET /settings/brand-slugs` — list page
  - `POST /settings/brand-slugs/add` — add new pair
  - `POST /settings/brand-slugs/{brand}/update` — change a slug
  - `POST /settings/brand-slugs/{brand}/delete` — remove a pair
- Site-header gear icon: small `<a href="/settings/brand-slugs" title="{{ t('nav.settings') }}">⚙</a>` placed just left of the language toggle in `templates/base.html`. Visible on every page.

Mockup of the header region:

```
┌──────────────────────────────────────────────────────────┐
│ [logo]                                          [⚙] [DE] │   ← gear next to lang toggle
└──────────────────────────────────────────────────────────┘
```

## Schema + Migration

New table in the existing SQLite DB:

```sql
CREATE TABLE IF NOT EXISTS brand_slugs (
  brand      TEXT PRIMARY KEY,   -- normalised (lowercased + trimmed)
  slug       TEXT NOT NULL,      -- normalised (lowercased + trimmed)
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`brand` is the primary key — uniqueness enforced at the DB layer; no app-level dedupe needed.

`execution/db.py:init_db()` is extended to:

1. Create the `brand_slugs` table (idempotent via `IF NOT EXISTS`)
2. Seed the table from the existing `BRAND_SLUGS` dict via `INSERT OR IGNORE` so user-edits are never overwritten:

```python
from execution.scraper import BRAND_SLUGS
for brand, slug in BRAND_SLUGS.items():
    conn.execute(
        "INSERT OR IGNORE INTO brand_slugs (brand, slug) VALUES (?, ?)",
        (brand, slug),
    )
```

After this iteration ships, `BRAND_SLUGS` in `execution/scraper.py` stays as seed data for fresh installs but is no longer read at request time. A comment on the dict documents the new role:

```python
# Seed data for the brand_slugs table. Read at app startup; not used at request
# time. See execution/brand_slugs.py for the runtime lookup.
```

## `brand_to_slug()` Rewrite

The function moves from `execution/scraper.py` to its own module so the scraper has no DB dependency for unrelated tasks. The new module also exposes CRUD helpers used by the settings page.

New file `execution/brand_slugs.py`:

```python
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
```

The two existing call sites — `main.py:304` (details_page route) and `navigation/lookup_router.py:9` (import) — change their import from `execution.scraper` to `execution.brand_slugs`. Same function signature; behaviour identical except the lookup source is the DB.

The old `brand_to_slug` function in `execution/scraper.py` is removed.

## Auto-Population on Successful Lookup

When a merlinssteine.de scrape **succeeds** for a brand+set_number pair, the resolved `(brand, slug)` is persisted to the `brand_slugs` table via `INSERT OR IGNORE`. Behaviour:

- Brand already in the table (LEGO, Pantasy, …) → no-op
- Brand is new (e.g. user added an "Ikea" set and merlinssteine knew it under `ikea-12345`) → row inserted with the slug that actually worked

Net effect: the settings page reflects every brand the user has successfully used. No manual entry required for brands whose name IS the slug. Brands whose slug differs from the name (Pantasy → `pant`, etc.) still need manual entry via the settings page if the initial scrape attempt with the fallback slug failed.

Implementation: in `navigation/lookup_router.py:_flow1`, after the merlinssteine `scrape_set` returns `status == "success"`, call:

```python
from execution.brand_slugs import add_brand_slug
try:
    add_brand_slug(brand, slug)
except sqlite3.IntegrityError:
    pass  # Brand already in table — expected, ignore
```

Or, more cleanly, use a dedicated helper `ensure_brand_slug(brand, slug)` in `execution/brand_slugs.py` that wraps `INSERT OR IGNORE`:

```python
def ensure_brand_slug(brand: str, slug: str) -> None:
    """Insert a brand → slug pair if not already present. Idempotent."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO brand_slugs (brand, slug) VALUES (?, ?)",
            (brand.lower().strip(), slug.lower().strip()),
        )
```

The `ensure_brand_slug` helper keeps `_flow1` clean (no exception handling) and matches the same `INSERT OR IGNORE` semantics used by the seed migration in `init_db()`. This is the variant we'll implement.

When a scrape **fails** (rate limit, 404, etc.), nothing is auto-added — we don't want to persist a guessed slug that didn't actually work.

## Page Layout

Simple two-section page: add form at top, list table below.

```
┌─────────────────────────────────────────────────────────────────────┐
│ Settings · Brand Slugs                                              │
├─────────────────────────────────────────────────────────────────────┤
│ Maps brand names to merlinssteine.de URL slugs. Brands not in this  │
│ list use the brand name itself (lowercased, spaces→hyphens).        │
├─────────────────────────────────────────────────────────────────────┤
│  Add new                                                            │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │ Brand        │  │ Slug         │   [ Add ]                       │
│  └──────────────┘  └──────────────┘                                 │
├─────────────────────────────────────────────────────────────────────┤
│  BRAND           │  SLUG          │                                 │
│  ────────────────┼────────────────┼─────────                        │
│  blue brixx      │  bb            │  [pencil] [trash]               │
│  bluebrixx       │  bb            │  [pencil] [trash]               │
│  cada            │  cada          │  [pencil] [trash]               │
│  cobi            │  cobi          │  [pencil] [trash]               │
│  funwhole        │  lumi          │  [pencil] [trash]               │
│  lego            │  lego          │  [pencil] [trash]               │
│  lumibricks      │  lumi          │  [pencil] [trash]               │
│  mould king      │  mk            │  [pencil] [trash]               │
│  pantasy         │  pant          │  [pencil] [trash]               │
└─────────────────────────────────────────────────────────────────────┘
```

### Interactions

- **Add new**: form at top with two inputs and an Add button → submits to `POST /settings/brand-slugs/add`. Redirects back to the same page; on success the new row appears in the table.
- **Edit (pencil)**: clicks → JS swaps that row's display cells for inputs (slug only — brand is the primary key and not editable) plus a save/cancel button pair. Submits inline via `fetch()` to `POST /settings/brand-slugs/{brand}/update`, then swaps back to display mode on success. To rename a brand, the user must delete + re-add.
- **Delete (trash)**: opens the existing `openDeleteModal` (already in `base.html`) with a tailored message → confirms → submits `POST /settings/brand-slugs/{brand}/delete` → reloads the page.
- **Form validation**: HTML `required` attribute on both inputs. Server validates non-empty after `.strip()`. Duplicate brand → flash error banner at top.
- **Empty state**: if the table has no rows (reachable if the user deletes every seed entry), show "No brand slugs configured yet. Add the first one above." in place of the table.

### Flash + error messaging

The page accepts optional `?error=duplicate&brand=X` or `?error=empty` query params, rendered as a callout-style banner at the top of the page. After a successful add/update/delete, the redirect URL is the plain `/settings/brand-slugs` (no flash needed — the table itself reflects the new state).

## i18n Keys

13 new keys in both `locales/en.json` and `locales/de.json`:

| Key | EN | DE |
|---|---|---|
| `nav.settings` | `Settings` | `Einstellungen` |
| `settings.brand_slugs.title` | `Brand Slugs` | `Marken-Slugs` |
| `settings.brand_slugs.intro` | `Maps brand names to merlinssteine.de URL slugs. Brands not in this list use the brand name itself (lowercased, spaces replaced with hyphens).` | `Ordnet Markennamen den merlinssteine.de-URL-Slugs zu. Marken, die hier nicht aufgeführt sind, verwenden den Markennamen direkt (kleingeschrieben, Leerzeichen werden zu Bindestrichen).` |
| `settings.brand_slugs.add_heading` | `Add new` | `Neu hinzufügen` |
| `settings.brand_slugs.col_brand` | `Brand` | `Marke` |
| `settings.brand_slugs.col_slug` | `Slug` | `Slug` |
| `settings.brand_slugs.add_button` | `Add` | `Hinzufügen` |
| `settings.brand_slugs.empty` | `No brand slugs configured yet. Add the first one above.` | `Noch keine Marken-Slugs konfiguriert. Füge oben den ersten hinzu.` |
| `settings.brand_slugs.error_duplicate` | `Brand "{brand}" already has a slug. Edit the existing row instead.` | `Marke "{brand}" hat bereits einen Slug. Bearbeite stattdessen den vorhandenen Eintrag.` |
| `settings.brand_slugs.error_empty` | `Brand and slug must both be non-empty.` | `Marke und Slug dürfen nicht leer sein.` |
| `settings.brand_slugs.delete_confirm` | `Really delete the slug mapping for "{brand}"?` | `Slug-Zuordnung für "{brand}" wirklich löschen?` |
| `settings.brand_slugs.save` | `Save` | `Speichern` |
| `settings.brand_slugs.cancel` | `Cancel` | `Abbrechen` |

## Files Touched

| File | Change |
|---|---|
| `execution/db.py` | Extend `init_db()` — create `brand_slugs` table + seed from `BRAND_SLUGS` dict |
| `execution/brand_slugs.py` | **New** — `brand_to_slug()` (DB-backed), `list_brand_slugs`, `add_brand_slug`, `ensure_brand_slug` (idempotent INSERT OR IGNORE), `update_brand_slug`, `delete_brand_slug` |
| `execution/scraper.py` | Keep `BRAND_SLUGS` dict (seed source); remove `brand_to_slug()` function; add comment explaining the dict's new role |
| `navigation/lookup_router.py` | Change import: `from execution.scraper import brand_to_slug, scrape_set` → split: `from execution.scraper import scrape_set` and `from execution.brand_slugs import brand_to_slug, ensure_brand_slug`. In `_flow1`, after a successful scrape, call `ensure_brand_slug(brand, slug)` to auto-populate the table. |
| `main.py` | Change lazy import in `details_page`: `from execution.scraper import brand_to_slug` → `from execution.brand_slugs import brand_to_slug`. Add four new routes (settings page + add/update/delete). |
| `templates/base.html` | Add gear-icon link to site header, just left of language toggle. Bump CSS cache buster. |
| `templates/settings_brand_slugs.html` | **New** — page with intro, add form, table, empty state, error banner |
| `static/style.css` | Small additions: `.settings-page`, `.brand-slug-table`, gear-icon styling. Cache buster bump `?v=6` → `?v=7`. |
| `locales/en.json`, `locales/de.json` | Add `nav.settings` + 12 keys under `settings.brand_slugs.*` |
| `tests/test_brand_slugs.py` | **New** — unit tests for the 5 functions in `execution/brand_slugs.py` |
| `tests/test_settings_routes.py` | **New** — TestClient smoke tests for the 4 new routes |

No new dependencies. Schema change is additive and idempotent.

## Tests

### `tests/test_brand_slugs.py`

- `test_brand_to_slug_returns_seeded_value` — `brand_to_slug("LEGO")` → `"lego"`, `brand_to_slug("Pantasy")` → `"pant"`
- `test_brand_to_slug_normalises_input` — `brand_to_slug("  LEGO  ")` → `"lego"`, `brand_to_slug("PANTASY")` → `"pant"`
- `test_brand_to_slug_falls_back_for_unknown` — `brand_to_slug("Some New Brand")` → `"some-new-brand"`
- `test_list_brand_slugs_returns_sorted_pairs`
- `test_add_brand_slug_inserts` — call `add_brand_slug("Foo Brand", "foo")` then `brand_to_slug("foo brand")` returns `"foo"`
- `test_add_brand_slug_duplicate_raises` — second `add_brand_slug` on same brand → `sqlite3.IntegrityError`
- `test_update_brand_slug_changes_slug`
- `test_update_brand_slug_for_missing_brand_is_noop`
- `test_delete_brand_slug_removes_row`
- `test_delete_brand_slug_for_missing_brand_is_noop`
- `test_ensure_brand_slug_inserts_when_missing` — `ensure_brand_slug("foo", "f")` adds the row; subsequent `brand_to_slug("foo")` returns `"f"`
- `test_ensure_brand_slug_noop_when_present` — calling `ensure_brand_slug("lego", "different-slug")` after the seed leaves `brand_to_slug("lego")` returning `"lego"` (the existing seed wins; ensure is idempotent and never overwrites)

### `tests/test_settings_routes.py`

- `test_settings_page_renders` — 200 + HTML + seeded rows visible
- `test_add_route_inserts_and_redirects`
- `test_add_route_duplicate_returns_error` — 200 + page with `?error=duplicate` callout, no insert
- `test_add_route_empty_returns_error` — 200 + page with `?error=empty` callout, no insert
- `test_update_route_changes_slug`
- `test_update_route_unknown_brand_redirects_silently`
- `test_delete_route_removes_row_and_redirects`

### Migration test

Extend the existing `tests/test_list_price_schema.py` pattern with a new file or test class:

- `test_brand_slugs_table_exists` — `PRAGMA table_info(brand_slugs)` lists `brand`, `slug`, `created_at`, `updated_at`
- `test_brand_slugs_seeded_from_dict` — after `init_db()`, `brand_to_slug("LEGO")` returns `"lego"`
- `test_brand_slugs_seed_does_not_overwrite_user_edits` — manually `UPDATE` a seeded slug, re-run `init_db()`, value is preserved

## Out of Scope

- Inline-when-lookup-fails prompt (the "B" approach from brainstorming — possible future Iteration 4.6)
- Multi-user / login (deferred; the gear icon location leaves room next to lang toggle for future "log in / my profile" controls)
- Bulk import/export of brand slugs (CSV upload, etc.)
- A general "settings hub" page (gear icon links directly to `/settings/brand-slugs` for now; could become a dropdown if more settings sections arrive)
- Validating that the slug actually resolves on merlinssteine.de (would require a live HTTP call; the user can verify by trying the lookup)

## Open Questions

None remaining. All decisions confirmed via brainstorming dialogue 2026-05-17.
