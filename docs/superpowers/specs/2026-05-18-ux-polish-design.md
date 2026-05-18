# UX Polish (Clone + Export) — Design

**Status:** Approved 2026-05-18
**Project:** brickset-tracker
**Iteration:** V1.1c (final V1.1 polish)

## Goal

Two user-facing wins that came out of V1 daily use, bundled into one iteration:

1. **"Clone this set" button** — duplicate a set's identity fields (brand, set number, name, part count, theme, etc.) into a new draft, leaving the instance fields (condition, location, purchase date, price paid, note, own_photos) blank. Makes multi-copy entry trivial.
2. **CSV + JSON export** — two download buttons on the collection list that dump the full collection as a backup or for spreadsheet analysis.

After this iteration ships, V1.1 is done and the next stop is the V2 handoff document.

## Out of Scope

- **Import** (the reverse direction — upload a JSON/CSV to recreate state). Could be a V2 feature.
- **Photo bytes** in the export. Only paths are included; image files stay on disk and are backed up separately.
- **Filtered/searched export** — explicitly rejected during brainstorm. The buttons always dump everything.

## Part 1: Clone this set

### Server-side change in `main.py`

Modify the existing `/add` route to accept an optional `?clone_from=<id>` query param. The current handler:

```python
@app.get("/add", response_class=HTMLResponse)
async def add_page(request: Request):
    return templates.TemplateResponse(request, "add.html", context=_ctx(
        request, prefill={}, callout=None, conditions=CONDITION_VALUES,
        brands=get_brands(), today=date.today().isoformat(),
    ))
```

becomes:

```python
@app.get("/add", response_class=HTMLResponse)
async def add_page(request: Request, clone_from: int | None = None):
    prefill: dict = {}
    if clone_from is not None:
        source = get_set(clone_from)
        if source is not None:
            # Clone IDENTITY fields only — leave instance fields blank
            # so the user records a separate purchase/build.
            prefill = {
                "brand":           source.get("brand"),
                "set_number":      source.get("set_number"),
                "name":            source.get("name"),
                "part_count":      source.get("part_count"),
                "theme":           source.get("theme"),
                "release_year":    source.get("release_year"),
                "ean":             source.get("ean"),
                "brickset_set_id": source.get("brickset_set_id"),
                "web_images":      source.get("web_images") or [],
                "minifigs":        source.get("minifigs"),
            }
        # If clone_from is provided but the source doesn't exist, fall back
        # to a blank /add page silently. Not worth a 404 for a malformed link.
    return templates.TemplateResponse(request, "add.html", context=_ctx(
        request, prefill=prefill, callout=None, conditions=CONDITION_VALUES,
        brands=get_brands(), today=date.today().isoformat(),
    ))
```

**Why these identity fields and not others:**

| Field | Cloned? | Reason |
|---|---|---|
| `brand` | ✓ | Same brand. |
| `set_number` | ✓ | Same set. |
| `name` | ✓ | Same product. |
| `part_count` | ✓ | Same physical configuration. |
| `theme` | ✓ | Same product line. |
| `release_year` | ✓ | Same product version. |
| `ean` | ✓ | Same barcode. |
| `brickset_set_id` | ✓ | Same Brickset reference. |
| `web_images` | ✓ | Same product photography. |
| `minifigs` | ✓ | Same minifig count. |
| `condition` | ✗ | The new copy may be in a different state. |
| `location` | ✗ | The new copy is somewhere else. |
| `date_of_purchase` | ✗ | Defaults to today via existing template logic. |
| `price_paid` | ✗ | New purchase, new price. |
| `list_price` | ✗ | Could differ if bought years apart. |
| `note` | ✗ | Free-text differentiation is exactly the point. |
| `own_photos` | ✗ | The user's own photos belong to a specific copy. |

### Template changes

**`templates/add.html`** — no JS change needed. The existing Jinja patterns (`{{ prefill.brand or '' }}`, `{{ prefill.set_number or '' }}`, etc., already throughout the form) consume whatever `prefill` dict the route hands them.

**`templates/_results_partial.html`** — extend the action row at line 87–101 with a Clone button between the existing edit and delete buttons:

```jinja
<a href="/add?clone_from={{ s.id }}" class="btn btn-ghost btn-sm" title="{{ t('actions.clone') }}">
  <i data-lucide="copy" style="width:13px;height:13px"></i>
</a>
```

**`templates/edit.html`** — the form-actions row at line 171–181 currently has Cancel on the left, a flex spacer, and Save on the right. Add a Clone button immediately after the Cancel link (before the spacer) so it sits on the left side, away from the primary Save action:

```jinja
  <div class="form-actions">
    <a href="/" class="btn btn-ghost">
      <i data-lucide="x" style="width:15px;height:15px"></i>
      {{ t('add.cancel') }}
    </a>
    <a href="/add?clone_from={{ set.id }}" class="btn btn-ghost" title="{{ t('actions.clone') }}">
      <i data-lucide="copy" style="width:15px;height:15px"></i>
      {{ t('actions.clone') }}
    </a>
    <span class="spacer"></span>
    <button type="submit" class="btn btn-primary">
      <i data-lucide="save" style="width:15px;height:15px"></i>
      {{ t('edit.save') }}
    </button>
  </div>
```

(Icon size matches the form-action buttons, not the smaller list-card buttons.)

### i18n

One new key per locale:

**`locales/de.json`**:
```json
"actions": {
  "clone": "Duplizieren"
}
```

**`locales/en.json`**:
```json
"actions": {
  "clone": "Clone this set"
}
```

If an `actions` namespace doesn't yet exist in the locale files, create it. Otherwise add `clone` under the existing namespace.

### Tests (`tests/test_clone_route.py`)

Three new tests:

1. **`test_clone_from_populates_identity_fields`** — seed a set with `brickset_set_id=23456`, `web_images=["url1", "url2"]`, `theme="Creator Expert"`, `release_year=2022`, etc. GET `/add?clone_from=<id>`. Assert the rendered HTML contains those values in the right form fields (use `<input ... value="...">` substring matching).
2. **`test_clone_from_skips_instance_fields`** — seed a set with `condition="gebaut"`, `location="Regal 5"`, `note="Sentimental"`, `price_paid=99.95`, `own_photos=["uploads/12/foo.jpg"]`. GET clone. Assert those values do NOT appear in the rendered form.
3. **`test_clone_from_invalid_id_falls_back_to_blank_add`** — GET `/add?clone_from=99999` against an empty DB. Assert HTTP 200 and the rendered page looks like a regular blank add page (no `selected` options, empty value inputs).

## Part 2: CSV + JSON Export

### Server-side routes in `main.py`

Two new GET routes near the other API routes. Both return `Content-Disposition: attachment` so browsers download.

**`GET /api/export/json`:**

```python
@app.get("/api/export/json")
async def api_export_json():
    """Full collection as JSON. Backup-friendly: nested fields stay as arrays."""
    import json
    rows = get_sets()  # No filters → full collection.
    body = json.dumps(rows, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    filename = f"brickset-tracker-{date.today().isoformat()}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**`GET /api/export/csv`:**

```python
@app.get("/api/export/csv")
async def api_export_csv():
    """Full collection as CSV. Spreadsheet-friendly: nested fields pipe-joined.
    Includes a UTF-8 BOM so Excel/Numbers detect the encoding correctly."""
    import csv
    import io

    rows = get_sets()
    columns = [
        "id", "brand", "set_number", "name", "part_count",
        "theme", "release_year", "ean", "brickset_set_id",
        "condition", "location", "date_of_purchase",
        "price_paid", "list_price", "minifigs", "note",
        "status", "created_at",
        "web_images", "own_photos",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        out = dict(row)
        out["web_images"] = "|".join(row.get("web_images") or [])
        out["own_photos"] = "|".join(row.get("own_photos") or [])
        writer.writerow(out)
    filename = f"brickset-tracker-{date.today().isoformat()}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),  # BOM for Excel
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**Implementation notes:**
- `get_sets()` already parses `web_images` and `own_photos` from the SQLite JSON-as-TEXT storage into real Python lists (via `_row_to_dict`), so `json.dumps` produces clean nested arrays and the `"|".join(...)` for CSV works directly.
- `ensure_ascii=False` keeps German content readable in JSON.
- `default=str` handles `date` objects (ISO format).
- `utf-8-sig` writes a UTF-8 BOM so Excel on macOS opens the CSV with the right encoding. Numbers.app and LibreOffice handle the BOM gracefully.
- `extrasaction="ignore"` means future field additions to `get_sets()` won't crash the CSV — they just don't appear until we explicitly add them to `columns`.
- Drafts are included in both exports. Backups should contain everything; the `status` column distinguishes them.
- `Response` is the FastAPI primitive (`fastapi.Response`), already imported by `main.py` for other routes. If not, add the import.

### UI affordances (`templates/index.html`)

Two download buttons in the page-header action row, alongside the existing "Add set" / "Brickset import" / gear icon links:

```jinja
<a href="/api/export/csv" class="btn btn-ghost" download>
  <i data-lucide="file-down" style="width:15px;height:15px"></i>
  {{ t('list.export_csv') }}
</a>
<a href="/api/export/json" class="btn btn-ghost" download>
  <i data-lucide="file-down" style="width:15px;height:15px"></i>
  {{ t('list.export_json') }}
</a>
```

The `download` HTML attribute is a browser hint; the actual filename comes from the server's `Content-Disposition` header. We use `download` rather than relying on header parsing because Safari handles inline content-disposition slightly differently across versions.

**Placement note**: the page header currently has "Add set", "Brickset import", and a gear icon. Adding two more inline buttons makes the row five wide. If that becomes visually crowded, a future iteration can collapse Export into a dropdown menu — out of scope here. For V1.1c, two inline buttons keep it simple and discoverable.

### i18n

Two new keys per locale, under the existing `list` namespace:

**`locales/de.json`**:
```json
"list": {
  ...existing keys...,
  "export_csv": "Als CSV",
  "export_json": "Als JSON"
}
```

**`locales/en.json`**:
```json
"list": {
  ...existing keys...,
  "export_csv": "Export CSV",
  "export_json": "Export JSON"
}
```

### Tests (`tests/test_export_routes.py`)

Five new tests:

1. **`test_export_json_returns_attachment_header`** — GET `/api/export/json`. Assert HTTP 200, `Content-Disposition` matches the pattern `attachment; filename="brickset-tracker-YYYY-MM-DD.json"` (with today's date), `Content-Type` starts with `application/json`.
2. **`test_export_json_includes_all_sets`** — seed 3 sets via `make_set` with distinct brands ("LEGO", "Cobi", "Pantasy"). GET, parse the body as JSON, assert it's a list of 3 dicts with the right brand values.
3. **`test_export_json_serialises_nested_fields_as_arrays`** — seed a set, then directly UPDATE its `web_images` column with `json.dumps(["http://a", "http://b"])`. GET, parse the JSON. Assert that row's `web_images` field is the Python list `["http://a", "http://b"]`, NOT a string.
4. **`test_export_csv_returns_attachment_with_bom`** — GET `/api/export/csv`. Assert headers (HTTP 200, `Content-Disposition` filename, `Content-Type: text/csv`). Assert the response body bytes start with `b"\xef\xbb\xbf"` (the UTF-8 BOM).
5. **`test_export_csv_serialises_nested_fields_as_pipes`** — seed a set, UPDATE `web_images` to `["http://a", "http://b"]` via JSON. GET CSV, parse it with `csv.DictReader` (after stripping the BOM with `.decode("utf-8-sig")`). Assert the `web_images` cell value is `"http://a|http://b"`.

## Files Touched (summary)

| File | Action |
|---|---|
| `main.py` | Add `clone_from` param to `add_page`; add 2 export routes. |
| `templates/_results_partial.html` | Add Clone icon to list-card actions. |
| `templates/edit.html` | Add Clone button to form-actions row. |
| `templates/index.html` | Add 2 Export buttons to page-header action row. |
| `locales/de.json` | Add `actions.clone`, `list.export_csv`, `list.export_json`. |
| `locales/en.json` | Add same 3 keys. |
| `tests/test_clone_route.py` | New. 3 tests. |
| `tests/test_export_routes.py` | New. 5 tests. |

8 new tests total. Test count goes from 159 → 167.

## Risk + Migration

- **No schema changes.** No data migration.
- **Backward compatible.** Existing `/add` users see no difference unless they include `?clone_from=<id>`.
- **Export endpoints are GET-only and read-only.** No way to corrupt state.
- **Stale clone source**: if you clone, then delete the source, the cloned form is unaffected (data already copied into the new draft).
- **Large collections**: with ~1000 sets, the JSON export stays well under 10 MB. No streaming needed.
- **CSV encoding**: UTF-8 BOM ensures Excel for Mac opens German content correctly. Numbers.app and LibreOffice handle the BOM gracefully.
- **i18n namespace creation**: if `actions` doesn't yet exist in the locale files, the implementer creates it; otherwise extends.

## Done When

- 3 Clone changes (route + 2 templates) land.
- 2 Export routes land.
- 5 i18n entries land (1 `actions.clone` + 2×2 `list.export_*`).
- 8 new tests pass; `pytest -q` reports **167 passed**.
- Manual smoke:
  - Clone a set with all fields populated → new `/add` form has identity fields filled, instance fields blank.
  - Clone a set, then save → results in a new row in the collection.
  - Click "Export CSV" → downloads `brickset-tracker-YYYY-MM-DD.csv`, opens in Numbers without Mojibake.
  - Click "Export JSON" → downloads `brickset-tracker-YYYY-MM-DD.json`, opens as valid JSON in any text editor.
- LaunchAgent server stays running (no restart needed; new routes picked up by FastAPI worker on next import).
- V1.1c marked complete in `task_plan.md`.
