# Iteration 3.5 — Brickset Bulk Import — Design

**Status:** Drafted 2026-05-16
**Project:** brickset-tracker
**Iteration:** 3.5 (between Iteration 3 search+filter and Iteration 4 details view)

## Goal

Pull the user's owned LEGO sets from Brickset into the local collection, with duplicate-aware semantics that respect the existing schema (one row per physical instance). Designed for the user's immediate need (28 Brickset-tracked sets to import) but reusable any time the Brickset side has gained sets not yet in local.

## Non-Goals

- Push (the existing per-row refresh-arrow sync button already handles push)
- Wishlist (`want=1`) imports — only `owned=1`
- merlinssteine.de enrichment during import (rate limit at 10/day would block the use case; user can enrich individual sets later via the edit page's "Fetch Data" button)
- Non-LEGO brands (Brickset is LEGO-only)

## User Flow

1. User navigates to `/import/brickset` (new page; reachable via a header link next to "Add Set").
2. Page shows a button "Fetch my Brickset collection".
3. Click → server calls Brickset's `getSets` with `owned=1` and the user's `userHash`. (One API call, multiple pages possible — handled below.)
4. Server renders a preview table listing every owned set Brickset returned.
5. For each row the user can:
   - Tick/untick the row (default: ticked)
   - Adjust the `Import: [N]` quantity (default: `max(0, bs_qty − local_qty)`)
6. User clicks "Import selected" at the bottom.
7. Server processes the import → redirects to `/` with a flash message: "Imported N new rows across M sets; backfilled brickset_set_id on K existing rows."

## UI Layout

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  Import from Brickset                                              [Cancel]   │
├───────────────────────────────────────────────────────────────────────────────┤
│  Brickset reported 30 owned sets. Will create 32 new rows across 28 sets;     │
│  will backfill brickset_set_id on 2 existing rows.                            │
├───────────────────────────────────────────────────────────────────────────────┤
│  [✓]  10298   Vespa 125            Creator Expert       2022                  │
│       ↳ Brickset: 1   Local: 0   Import: [ 1 ]                                │
├───────────────────────────────────────────────────────────────────────────────┤
│  [✓]  31140   Magical Unicorn      Creator              2021                  │
│       ↳ Brickset: 3   Local: 0   Import: [ 3 ]                                │
├───────────────────────────────────────────────────────────────────────────────┤
│  [✓]  42171   McLaren P1           Technic              2023                  │
│       ↳ Brickset: 1   Local: 2   Import: [ 0 ]                                │
│       Local has more — sync any row to push 2 back to Brickset                │
├───────────────────────────────────────────────────────────────────────────────┤
│  [✓]  42225   Yellow Motorcycle    Technic              2026                  │
│       ↳ Brickset: 1   Local: 1   Import: [ 0 ]                                │
│       Set already complete — will backfill brickset_set_id if missing         │
├───────────────────────────────────────────────────────────────────────────────┤
│  ... (28 more rows) ...                                                       │
├───────────────────────────────────────────────────────────────────────────────┤
│                                          [Import selected (32 rows)]          │
└───────────────────────────────────────────────────────────────────────────────┘
```

- Per-row checkbox: ticked = include this row in import; unticked = skip the row entirely (including the `brickset_set_id` backfill).
- `Import: [N]` is an `<input type="number" min="0">` field; updates the bottom counter live via JS.
- Summary line at top updates as the user edits counts/checkboxes.
- Final button label reflects the current total: "Import selected (N rows)".

## Row States

Each preview row falls into one of four categories. Category determines the default `Import: [N]` value and the helper text below the row.

| Category | When | Default Import N | Helper text |
|---|---|---|---|
| **New** | `local_qty == 0` | `bs_qty` | (none) |
| **Partial merge** | `0 < local_qty < bs_qty` | `bs_qty − local_qty` | "Local has fewer — adding the difference" |
| **Already covered** | `local_qty == bs_qty` | `0` | "Already in collection — will backfill brickset_set_id if missing" |
| **Local-richer** | `local_qty > bs_qty` | `0` | "Local has more — sync any row to push N back to Brickset" |

In all four categories, on confirm:
- `Import: [N]` controls how many NEW rows to insert.
- Any existing local rows for that `brand+set_number` that lack a `brickset_set_id` get it filled in (provided the row is ticked).

## Data Flow

### Fetch step

```
POST /api/import/brickset/fetch
  → calls execution.brickset.fetch_owned_collection() (new)
    → calls Brickset getSets with {owned=1, pageSize=500, pageNumber=N}
    → pages until fewer than pageSize results return
  → for each Brickset set, computes local_qty via count_owned(brand, set_number)
  → returns list[dict] of preview rows
```

Each preview row dict shape:

```python
{
    "brickset_set_id": 23456,           # from setID
    "set_number":      "10298",         # from "number" field (Brickset's bare number)
    "brand":           "LEGO",          # hardcoded — Brickset is LEGO-only
    "name":            "Vespa 125",
    "part_count":      1106,            # from pieces
    "theme":           "Creator Expert",
    "release_year":    2022,
    "ean":             "5702016912661",
    "image_url":       "https://...",
    "bs_qty":          1,               # from qtyOwned in the response (or 1 fallback)
    "local_qty":       0,               # from count_owned()
    "local_ids_missing_bs_id": [4, 17], # local row ids that have NULL brickset_set_id
}
```

### Commit step

```
POST /api/import/brickset/commit
  Form data: list of row payloads (only ticked rows), each with import_qty (int)
  → for each row:
    → if local_ids_missing_bs_id:
      → UPDATE sets SET brickset_set_id=? WHERE id IN (...)
    → for i in range(import_qty):
      → INSERT new row with Brickset metadata + status='complete'
                              + note=f"Imported from Brickset on {today}"
  → returns {created: N, backfilled: K}
  → redirect to / with flash message
```

## Backend

### `execution/brickset.py`

New async function:

```python
async def fetch_owned_collection() -> dict:
    """Return all sets the user owns according to Brickset.

    Pages through getSets with owned=1 until fewer than pageSize results
    return. Consumes one quota point per page.

    Returns:
        {"status": "ok", "sets": [...]}      on success
        {"status": "quota_exceeded"}         when quota is exhausted mid-paging
        {"status": "error", "message": "..."} on network/API failure
    """
```

Implementation notes:
- `pageSize=100` (conservative; well within Brickset's per-page max). For 30 sets the user only needs 1 page.
- Brickset's getSets accepts both `params` (a JSON-stringified dict) and an `userHash`. With `owned=1` in params it returns owned sets; with `userHash` it's the user's collection.
- Pagination: loop with `pageNumber=1,2,3,...` until `len(returned_sets) < pageSize`.
- Each page consumes one Brickset quota point.

Each returned set is mapped through the existing `_map_set` helper plus the new `qtyOwned` extraction:

```python
def _map_owned_set(s: dict) -> dict:
    """Extension of _map_set that also extracts qtyOwned from collection.qtyOwned."""
    base = _map_set(s)
    coll = s.get("collection") or {}
    base["qty_owned"] = coll.get("qtyOwned") or 1   # 1 is a defensive default
    base["set_number"] = s.get("number") or base.get("set_number")
    return base
```

(Brickset's getSets response includes a `collection` object on each set when `userHash` is provided — that's where `qtyOwned` lives.)

### `navigation/set_manager.py`

New helper to find local rows of a given set with missing `brickset_set_id`:

```python
def find_local_rows_missing_brickset_id(brand: str, set_number: str) -> list[int]:
    """Return ids of local rows matching brand+set_number that lack a brickset_set_id."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id FROM sets WHERE brand=? AND set_number=? AND brickset_set_id IS NULL",
            (brand, set_number),
        ).fetchall()
    return [r["id"] for r in rows]
```

New helper to commit the import:

```python
def commit_import_rows(rows: list[dict]) -> dict:
    """Persist imported rows. Each row dict has:
       brand, set_number, name, part_count, theme, release_year, ean,
       web_images (list), brickset_set_id, import_qty,
       local_ids_missing_bs_id (list[int]).

    Behaviour per row:
      - For each id in local_ids_missing_bs_id: UPDATE that row's brickset_set_id
      - For i in range(import_qty): INSERT a new row with the Brickset metadata

    Returns {"created": N, "backfilled": K}.
    """
```

The new rows get:
- `status = 'complete'`
- `note = f"Imported from Brickset on {date.today().isoformat()}"`
- `date_of_purchase = None` (deliberately blank — user fills later)
- `condition`, `location`, `price_paid` = None (same reason)
- `created_at`/`updated_at` = `datetime('now')`

### `main.py`

Three new routes:

```python
@app.get("/import/brickset", response_class=HTMLResponse)
async def import_page(request: Request):
    """Renders the empty import page with a 'Fetch' button."""

@app.post("/api/import/brickset/fetch", response_class=HTMLResponse)
async def import_fetch(request: Request):
    """Calls fetch_owned_collection, computes per-row preview data,
    returns the preview table as an HTML partial."""

@app.post("/api/import/brickset/commit")
async def import_commit(request: Request):
    """Parses the form payload (ticked rows + import_qty per row),
    calls commit_import_rows, redirects to / with a flash message."""
```

The commit redirects via `RedirectResponse` and uses a query-string flash mechanism (`/?imported=N&backfilled=K`) since the project has no existing flash/session infrastructure and adding one is out of scope. The `/` route reads these params and renders a one-time banner.

## Templates

### `templates/import_brickset.html` (new)

- Extends `base.html`
- Page header: "Import from Brickset", with a "Cancel" link back to `/`
- Body has two sections, only one visible at a time:
  - **Initial:** large "Fetch my Brickset collection" button + explanatory paragraph
  - **Preview:** the summary line + table of rows + "Import selected" button
- After fetch, JS swaps the initial section out and the preview section in (no full page reload — keeps the rate-limit context clear if the user backs out).

### `templates/_brickset_import_preview.html` (new partial)

The preview table content, rendered server-side after the fetch. Returned by `/api/import/brickset/fetch`.

## i18n

New keys in `locales/de.json` and `locales/en.json`:

| Key | EN | DE |
|---|---|---|
| `import.title` | `Import from Brickset` | `Aus Brickset importieren` |
| `import.fetch_button` | `Fetch my Brickset collection` | `Meine Brickset-Sammlung abrufen` |
| `import.fetching` | `Fetching...` | `Wird abgerufen...` |
| `import.intro` | `This will pull every set you've marked as owned on Brickset and let you preview before importing.` | `Hierbei werden alle Sets, die du auf Brickset als eigen markiert hast, abgerufen und zur Vorschau angezeigt.` |
| `import.summary` | `Brickset reported {bs_total} owned sets. Will create {will_create} new rows across {sets_count} sets; will backfill brickset_set_id on {will_backfill} existing rows.` | `Brickset meldet {bs_total} eigene Sets. {will_create} neue Einträge in {sets_count} Sets werden erstellt; brickset_set_id wird bei {will_backfill} bestehenden Einträgen ergänzt.` |
| `import.col_bs_qty` | `Brickset` | `Brickset` |
| `import.col_local_qty` | `Local` | `Lokal` |
| `import.col_import` | `Import` | `Importieren` |
| `import.hint_partial` | `Local has fewer — adding the difference` | `Lokal weniger — Differenz wird ergänzt` |
| `import.hint_already_covered` | `Already in collection — will backfill brickset_set_id if missing` | `Bereits in Sammlung — brickset_set_id wird ggf. ergänzt` |
| `import.hint_local_richer` | `Local has more — sync any row to push {diff} back to Brickset` | `Lokal mehr — eine Zeile synchronisieren, um {diff} zurück an Brickset zu senden` |
| `import.submit_button` | `Import selected ({n} rows)` | `Auswahl importieren ({n} Einträge)` |
| `import.flash_success` | `Imported {created} new rows; backfilled brickset_set_id on {backfilled} existing rows.` | `{created} neue Einträge importiert; brickset_set_id bei {backfilled} bestehenden Einträgen ergänzt.` |
| `import.error_quota` | `Brickset API daily quota exhausted. Try again tomorrow.` | `Brickset-API-Tageslimit erschöpft. Bitte morgen erneut versuchen.` |
| `import.error_fetch` | `Could not reach Brickset: {message}` | `Brickset nicht erreichbar: {message}` |
| `nav.import_brickset` | `Import from Brickset` | `Aus Brickset importieren` |

## Header Navigation

Add a discreet "Import from Brickset" link in the page header next to the existing "+ Add Set" button. It's not a primary action — most days you won't use it — but it shouldn't be hidden.

For simplicity: render it only when `quota.brickset.remaining > 0` (so when the API is unusable, the link disappears).

## Styling

Reuse existing tokens. Net new CSS for:

- `.import-preview-row` — single row card; tightly packed
- `.import-preview-row__qty` — small inline form for the `Import: [N]` input
- `.import-preview-row__hint` — italicised small text under the main row

Approximately 40 lines of CSS in `static/style.css`. Bump cache buster to `?v=4`.

## Edge Cases

- **Brickset's response includes a set we can't categorise (no `number`, missing essential fields):** skip with a server-log warning; don't surface in preview.
- **User exhausts Brickset quota mid-paging:** preview shows partial results with a warning banner: "Some sets may be missing — quota exhausted. Try again tomorrow."
- **User commits but a row's `local_ids_missing_bs_id` includes an id that's since been deleted:** the `UPDATE ... WHERE id IN (...)` no-ops cleanly; no error. Returned `backfilled` count reflects rows actually updated (via `cursor.rowcount`).
- **Duplicate imports:** if the user runs the import twice, the second run finds:
  - All "new" rows from the first run are now in the DB → those sets show up as "already covered" with `Import: 0` (default).
  - No accidental duplication unless the user manually raises the count.
- **EAN already cached:** the importer also writes to `ean_cache` (source = `"brickset_import"`) so future scans of these EANs resolve instantly.
- **Image URL fetched at import is cached at request time:** new rows store the Brickset image URL in `web_images`. The existing `/api/proxy-image` endpoint handles serving it (so no need for the importer to download images).
- **Form-tampering trust model:** the preview form transmits each row's Brickset metadata (name, theme, etc.) back to the commit endpoint, so the server doesn't need to re-fetch from Brickset (saves quota and avoids a second round-trip). Because this app is local-only with a single user, we trust the form payload. Server still validates that `set_number` and `brand` are non-empty and `import_qty` is a non-negative integer; any row failing these checks is silently skipped.

## Out of Scope for Iteration 3.5

- Wishlist (`want=1`) import
- merlinssteine.de enrichment during import (rate-limit incompatible)
- "Pull updates" mode — overwriting local metadata when Brickset has newer data (would violate "never silent data loss"; defer to a future iteration with explicit per-field merge UI)
- Non-LEGO bulk import (the existing single-set lookup flow handles other brands)

## Files Touched

| File | Change |
|---|---|
| `execution/brickset.py` | Add `fetch_owned_collection()`, `_map_owned_set()` |
| `navigation/set_manager.py` | Add `find_local_rows_missing_brickset_id()`, `commit_import_rows()` |
| `main.py` | Add three new routes: `/import/brickset` (GET), `/api/import/brickset/fetch` (POST, returns HTML partial), `/api/import/brickset/commit` (POST, redirects) |
| `templates/import_brickset.html` | **New** — page shell with initial-state + preview-state sections |
| `templates/_brickset_import_preview.html` | **New** — server-rendered preview table partial |
| `templates/base.html` | Add "Import from Brickset" link in header (conditional on quota) + bump CSS cache buster |
| `templates/index.html` | Render flash banner if `?imported=N&backfilled=K` in URL |
| `static/style.css` | New styles for import preview rows |
| `locales/de.json`, `locales/en.json` | Add ~14 new keys |

No DB migration. The `sets` table already supports everything required (status='complete', brickset_set_id column, note column).

## Open Questions

None remaining. All design decisions confirmed via brainstorming dialogue 2026-05-16.

## Future-related Loose Ends (tracked separately)

- **"Clone this set" button** — surfaced during this design. Tracked in `MEMORY/task_plan.md` under "Decide during code review". Would pair naturally with multi-copy semantics by letting users add the 4th/5th copy via clone instead of full re-entry.
