# Code-Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 10 fixes (F1–F5, S1–S5) specified in `docs/superpowers/specs/2026-05-17-code-review-fixes-design.md`, in dependency order, one TDD task per fix.

**Architecture:** No new modules. Edits to `main.py`, `navigation/set_manager.py`, `navigation/lookup_router.py`, `execution/brickset.py`, three templates, and two locale files. One small factory extension to enable F2/F3 tests.

**Tech Stack:** FastAPI 0.115 / Starlette 0.46, Jinja2 3.1 (with built-in `tojson` filter), SQLite via stdlib `sqlite3`, pytest + monkeypatched `db` fixture.

---

## File Structure

| File | Owns |
|---|---|
| `tests/factories.py` | Extended with `brickset_set_id` keyword (needed by F2/F3 tests). |
| `tests/test_brickset_import_preview_xss.py` | F1 test (new file). |
| `tests/test_map_owned_set.py` | F4 test (existing file — append). |
| `tests/test_import_routes.py` | F2 test (existing file — append). |
| `tests/test_commit_import_rows.py` | F3 tests (existing file — append + amend existing tests). |
| `tests/test_api_upload.py` | F5 test (new file). |
| `tests/test_set_manager_delete.py` | S1 test (new file). |
| `tests/test_set_manager_update.py` | S2 test (new file). |
| `tests/test_lookup_router_duplicates.py` | S3 test (new file). |
| `tests/test_import_routes.py` | S4 test (existing file — append). |
| `templates/_brickset_import_preview.html` | F1 fix. |
| `execution/brickset.py` | F4 fix. |
| `main.py` | F1 (payload dict), F2 (re-derive ids), F3 (payload `preview_local_qty`), F5 (regex), S4 (preserve 0). |
| `navigation/set_manager.py` | F3 (idempotent insert), S1 (rmtree on delete), S2 (unlink removed). |
| `navigation/lookup_router.py` | S3 (populate prefill). |
| `templates/add.html` | S3 wire-up (existing `showDuplicateWarning` already consumes a list; only the route was missing). |
| `templates/edit.html` | S5 status callout. |
| `locales/en.json`, `locales/de.json` | S3 (i18n key reused — `errors.duplicate_warning` already exists with the `{count}` placeholder; the spec's "delete dead key" turns into "keep and reuse"). |

### Spec deviation: `errors.duplicate_warning` is reused, not deleted

While exploring the codebase I found `errors.duplicate_warning` already exists in both locale files with the desired `{count}` placeholder (`locales/en.json:46`, `locales/de.json:46`) AND the add page already has a `<div id="duplicate-callout">` element AND a `showDuplicateWarning(dupes)` JS function — they all simply have no producer in the route. The spec assumed the key was dead; in fact only the producer was. So the S3 work shrinks to:
1. Populate `prefill["duplicates"]` as a list in `lookup_router.py:_flow1`.
2. Replace the hardcoded German/English string in `showDuplicateWarning` with a call into the i18n `t()` helper using the existing key.

No new locale key. The "delete dead key" cleanup item disappears.

### Spec deviation: F3 needs an extra payload field

The spec formula `actual_insert = max(0, import_qty - current_local_count)` reinterprets `import_qty` as "desired total ownership," but the UI computes it as a delta (`default_import_qty = max(0, bs_qty - local_qty)`). To make F3 robust without changing the UI's mental model, the row payload also carries `preview_local_qty` (the local count at preview time, which `main.py` already computes). The server formula becomes:

```python
delta_already_imported = max(0, current_local_count - preview_local_qty)
actual_insert = max(0, import_qty - delta_already_imported)
```

- **Happy path:** preview=0, current=0, import_qty=3 → insert 3 ✓
- **Double-submit retry:** preview=0, current=3 (after first commit), import_qty=3 → insert 0 ✓
- **Two browser tabs:** tab A imports 3 first; tab B's preview=0, current=3, import_qty=3 → insert 0 ✓
- **User edits qty up:** preview=0, current=0, import_qty=5 → insert 5 ✓

This is the only spec deviation in F3; the test added by Task 4 covers it.

---

## Task 0: Extend `make_set` factory to support `brickset_set_id`

Several upcoming tests need to seed rows that either have or lack `brickset_set_id`. Add the keyword once.

**Files:**
- Modify: `tests/factories.py`

- [ ] **Step 1: Add `brickset_set_id` parameter to `make_set`**

Edit `tests/factories.py` — change the signature and INSERT:

```python
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
    brickset_set_id: int | None = None,
    status: str = "complete",
) -> int:
    """Insert a set row and return its id."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO sets
               (brand, set_number, name, part_count, condition, location,
                date_of_purchase, note, theme, release_year, minifigs,
                price_paid, list_price, ean, brickset_set_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (brand, set_number, name, part_count, condition, location,
             date_of_purchase, note, theme, release_year, minifigs,
             price_paid, list_price, ean, brickset_set_id, status),
        )
        return cur.lastrowid
```

- [ ] **Step 2: Run the full suite to confirm no regression**

```bash
pytest -q
```

Expected: All ~133 existing tests still pass (keyword is optional with `None` default; existing callers unchanged).

- [ ] **Step 3: Commit**

```bash
git add tests/factories.py
git commit -m "test(factories): add brickset_set_id keyword to make_set"
```

---

## Task 1: F1 — XSS-escape JSON in the import preview

The Brickset preview embeds a JSON payload inside a `<script type="application/json">` tag using `{{ row.payload_json | safe }}`. A set name containing `</script>` would terminate the element. Switch to Jinja's `tojson` filter (which escapes `<`, `>`, `&`, `'` as `\uXXXX`) and pass the dict directly.

**Files:**
- Test: `tests/test_brickset_import_preview_xss.py` (new)
- Modify: `main.py` (around line 178–200 — the payload-building block in `api_import_fetch`)
- Modify: `templates/_brickset_import_preview.html` (line 70)

- [ ] **Step 1: Write the failing test**

Create `tests/test_brickset_import_preview_xss.py`:

```python
"""F1 — Brickset preview must not allow </script> injection via set names."""
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _malicious_owned_collection():
    return {
        "status": "ok",
        "sets": [{
            "set_number": "10298",
            "set_id":     23456,
            # Crafted name: closing the script tag would let HTML escape.
            "name":       "Vespa </script><script>alert(1)</script>",
            "pieces":     1106,
            "theme":      "Creator Expert",
            "year":       2022,
            "ean":        None,
            "image_url":  None,
            "qty_owned":  1,
        }],
    }


def test_preview_escapes_script_terminator_in_payload(db):
    from main import app
    with patch("execution.brickset.fetch_owned_collection",
               new=AsyncMock(return_value=_malicious_owned_collection())):
        with TestClient(app) as client:
            r = client.post("/api/import/brickset/fetch")

    assert r.status_code == 200
    html = r.text
    # The raw </script> substring must NOT appear anywhere inside the
    # rendered payload (Jinja's tojson escapes < as <).
    # We sanity-check both: the escaped form appears, the raw form does not
    # appear inside a <script> block.
    assert "\\u003c/script\\u003e" in html or "\\u003c/script>" in html
    # The unescaped variant must not appear adjacent to the script-tag opening:
    assert "</script><script>alert(1)</script>" not in html
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_brickset_import_preview_xss.py -v
```

Expected: FAIL — `</script><script>alert(1)</script>` is present in the rendered HTML because `| safe` skips escaping.

- [ ] **Step 3: Change the template to use `tojson`**

Edit `templates/_brickset_import_preview.html` line 70:

```jinja
{# Hidden payload — server commits using these values #}
<script type="application/json" class="import-row-payload">
  {{ row.payload | tojson }}
</script>
```

(Changed: `row.payload_json | safe` → `row.payload | tojson`.)

- [ ] **Step 4: Pass the dict (not the JSON string) in `main.py`**

In `main.py` inside `api_import_fetch` (around line 178–201), change the row dict so it carries `payload` instead of `payload_json`. Remove the `json.dumps(...)` line. The block becomes:

```python
        payload = {
            "brand":           brand,
            "set_number":      set_number,
            "name":            s.get("name") or "",
            "part_count":      s.get("pieces"),
            "theme":           s.get("theme"),
            "release_year":    s.get("year"),
            "ean":             s.get("ean"),
            "web_images":      [s["image_url"]] if s.get("image_url") else [],
            "brickset_set_id": s["set_id"],
            "local_ids_missing_bs_id": missing_ids,
        }
        rows.append({
            "set_number":         set_number,
            "name":               s.get("name") or "",
            "theme":              s.get("theme"),
            "release_year":       s.get("year"),
            "part_count":         s.get("pieces"),
            "bs_qty":             bs_qty,
            "local_qty":          local_qty,
            "default_import_qty": default_import_qty,
            "hint_key":           hint_key,
            "payload":            payload,
        })
```

Also remove the now-unused `import json` import inside the function (line 137) if no other code in the function needs it — verify there isn't one elsewhere in the function body first. If `json` is needed elsewhere in the file at module level, leave the module-level import.

Check:

```bash
grep -n "json\." main.py | head -20
```

If `json.` appears anywhere else in `api_import_fetch`, keep its local import. Otherwise delete the `import json` line inside that handler.

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/test_brickset_import_preview_xss.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the full suite to confirm no regression**

```bash
pytest -q
```

Expected: All previous tests still pass (the import-preview test file expects `row.payload_json` only if any test hard-codes that — verify by grepping).

```bash
grep -rn "payload_json" tests/
```

If any test mentions `payload_json`, update it to `payload`. (Likely there are none — this was an internal name passed only from `main.py` to the template.)

- [ ] **Step 7: Commit**

```bash
git add main.py templates/_brickset_import_preview.html tests/test_brickset_import_preview_xss.py
git commit -m "fix(import): escape preview payload with tojson to prevent XSS (F1)"
```

---

## Task 2: F4 — Strip Brickset variant suffix in `_map_owned_set`

Brickset returns numbers like `10298-1`. `_map_owned_set` currently puts that raw value into `set_number`, so duplicate-detection against local rows entered as bare `10298` fails. Strip the `-N` suffix only on the `set_number` field; keep `brickset_set_id` as-is (it's stored separately and Brickset needs the suffix for round-trip calls).

**Files:**
- Test: `tests/test_map_owned_set.py` (append)
- Modify: `execution/brickset.py:180-193` (the `_map_owned_set` function)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_map_owned_set.py`:

```python
def test_variant_suffix_stripped_from_set_number():
    """F4 — Brickset's '-1' variant suffix must not leak into set_number,
    which the importer uses to match local rows entered as bare numbers."""
    from execution.brickset import _map_owned_set
    raw = {
        "setID":   23456,
        "number":  "10298-1",
        "name":    "Vespa 125",
        "pieces":  1106,
        "theme":   "Creator Expert",
        "year":    2022,
        "image":   {"imageURL": None},
        "LEGOCom": {"DE": {}},
        "collection": {"qtyOwned": 1},
    }
    result = _map_owned_set(raw)
    assert result["set_number"] == "10298"
    # brickset_set_id stays numeric/internal (from setID); not affected.


def test_set_number_without_suffix_passes_through():
    """A bare number from Brickset (no -N variant) must not be mangled."""
    from execution.brickset import _map_owned_set
    raw = {
        "setID": 9999, "number": "42171", "name": "x", "pieces": 1,
        "theme": "t", "year": 2024,
        "image": {"imageURL": None}, "LEGOCom": {"DE": {}},
        "collection": {"qtyOwned": 1},
    }
    assert _map_owned_set(raw)["set_number"] == "42171"


def test_set_number_empty_string_returns_empty_string():
    """Defensive: an empty 'number' must not crash on split('-')."""
    from execution.brickset import _map_owned_set
    raw = {
        "setID": 0, "number": "", "name": "", "pieces": 0,
        "theme": None, "year": None,
        "image": {"imageURL": None}, "LEGOCom": {"DE": {}},
        "collection": {"qtyOwned": 0},
    }
    assert _map_owned_set(raw)["set_number"] == ""
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_map_owned_set.py::test_variant_suffix_stripped_from_set_number -v
```

Expected: FAIL — current code returns `"10298-1"`, not `"10298"`.

- [ ] **Step 3: Implement the fix**

Edit `execution/brickset.py:192` — replace:

```python
    base["set_number"]  = s.get("number")
```

with:

```python
    raw_number = s.get("number") or ""
    base["set_number"]  = raw_number.split("-", 1)[0]
```

Use `split("-", 1)[0]` rather than `split("-")[0]` so a (hypothetical) hyphen in some future format only splits once. Same result for `10298-1` → `10298`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_map_owned_set.py -v
```

Expected: PASS for new tests + all existing tests in this file still pass.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: No regressions. (If the existing `test_fetch_owned_collection.py` hard-codes a `number` with a suffix and asserts it round-trips with the suffix, update that assertion.)

- [ ] **Step 6: Commit**

```bash
git add execution/brickset.py tests/test_map_owned_set.py
git commit -m "fix(brickset): strip variant suffix from set_number in _map_owned_set (F4)"
```

---

## Task 3: F2 — Re-derive `local_ids_missing_bs_id` server-side on commit

The commit handler currently trusts the client-submitted `local_ids_missing_bs_id`. A tampered or stale payload could update a brickset_set_id on an unrelated local row. Fix in the route layer: ignore the client value, recompute via `find_local_rows_missing_brickset_id(brand, set_number)` immediately before invoking `commit_import_rows`.

**Files:**
- Test: `tests/test_import_routes.py` (append)
- Modify: `main.py` (around line 252–264 in `api_import_commit`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_import_routes.py`:

```python
def test_commit_ignores_tampered_local_ids_missing_bs_id(db):
    """F2 — A client must not be able to backfill brickset_set_id onto a
    row of a different brand+set_number by passing a tampered id list."""
    from tests.factories import make_set
    from fastapi.testclient import TestClient
    from main import app
    from execution.db import get_connection

    # Victim: an UNRELATED row that the attacker is trying to corrupt.
    victim_id = make_set(brand="LEGO", set_number="99999", brickset_set_id=None)
    # Legitimate row to backfill (matches the payload's brand+set_number):
    legit_id  = make_set(brand="LEGO", set_number="10298", brickset_set_id=None)

    body = {
        "rows": [{
            "brand":           "LEGO",
            "set_number":      "10298",
            "name":            "Vespa",
            "part_count":      1106,
            "theme":           "Creator Expert",
            "release_year":    2022,
            "ean":             None,
            "web_images":      [],
            "brickset_set_id": 23456,
            "import_qty":      0,
            # Tampered: includes the victim's id alongside the legit id.
            "local_ids_missing_bs_id": [victim_id, legit_id],
            "preview_local_qty": 1,
        }],
    }

    with TestClient(app) as client:
        client.post("/api/import/brickset/commit", json=body)

    with get_connection() as conn:
        victim = conn.execute(
            "SELECT brickset_set_id FROM sets WHERE id=?", (victim_id,)
        ).fetchone()
        legit  = conn.execute(
            "SELECT brickset_set_id FROM sets WHERE id=?", (legit_id,)
        ).fetchone()

    assert victim["brickset_set_id"] is None, "Tampered id list must not touch unrelated rows"
    assert legit["brickset_set_id"] == 23456,  "Legit row must still be backfilled"
```

(The `preview_local_qty` field is referenced ahead — it's added in Task 4 and ignored here. Pre-adding it now keeps the test stable when Task 4 lands.)

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_import_routes.py::test_commit_ignores_tampered_local_ids_missing_bs_id -v
```

Expected: FAIL — `victim["brickset_set_id"]` becomes `23456` because the route blindly trusts the client list.

- [ ] **Step 3: Re-derive the id list server-side in the route**

Edit `main.py` inside `api_import_commit` (around line 229–264). The change: stop reading `local_ids_missing_bs_id` from the client payload, recompute it from the DB.

Replace this block:

```python
        sanitised.append({
            "brand":                   str(row["brand"]),
            "set_number":              str(row["set_number"]),
            "name":                    row.get("name") or "",
            "part_count":              part_count,
            "theme":                   row.get("theme"),
            "release_year":            row.get("release_year"),
            "ean":                     row.get("ean"),
            "web_images":              row.get("web_images") or [],
            "brickset_set_id":         int(row["brickset_set_id"]),
            "import_qty":              qty,
            "local_ids_missing_bs_id": [int(x) for x in (row.get("local_ids_missing_bs_id") or [])],
        })
```

with:

```python
        # F2: re-derive missing-id list from the DB; ignore client payload.
        from navigation.set_manager import find_local_rows_missing_brickset_id
        missing_ids = find_local_rows_missing_brickset_id(
            str(row["brand"]), str(row["set_number"])
        )

        sanitised.append({
            "brand":                   str(row["brand"]),
            "set_number":              str(row["set_number"]),
            "name":                    row.get("name") or "",
            "part_count":              part_count,
            "theme":                   row.get("theme"),
            "release_year":            row.get("release_year"),
            "ean":                     row.get("ean"),
            "web_images":              row.get("web_images") or [],
            "brickset_set_id":         int(row["brickset_set_id"]),
            "import_qty":              qty,
            "local_ids_missing_bs_id": missing_ids,
        })
```

Note: the `from navigation.set_manager import ...` line inside the function body is fine — the existing handler already does this pattern (line 139 in `api_import_fetch`). Alternatively, hoist it to a module-level import. Either is acceptable.

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_import_routes.py::test_commit_ignores_tampered_local_ids_missing_bs_id -v
```

Expected: PASS.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: All tests pass. Existing route-level tests still work because legitimate clients send the right id list anyway, and the server-derived value matches it.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_import_routes.py
git commit -m "fix(import): re-derive local_ids_missing_bs_id server-side on commit (F2)"
```

---

## Task 4: F3 — Idempotent commit (re-submit becomes a no-op)

Inside `commit_import_rows`, gate the INSERT loop on `actual_insert = max(0, import_qty - delta_already_imported)` where `delta_already_imported = max(0, current_local_count - preview_local_qty)`. Requires a new payload field `preview_local_qty` carried from preview → form → commit.

**Files:**
- Test: `tests/test_commit_import_rows.py` (append + amend)
- Modify: `main.py` (preview-row payload + commit sanitisation)
- Modify: `navigation/set_manager.py:commit_import_rows`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_commit_import_rows.py`:

```python
def test_commit_is_idempotent_on_double_submit(db):
    """F3 — Re-submitting the same payload after a successful commit inserts 0 new rows."""
    row = _vespa_row(import_qty=3)
    row["preview_local_qty"] = 0  # snapshot: nothing locally at preview time

    first  = commit_import_rows([row])
    second = commit_import_rows([row])

    assert first["created"]  == 3
    assert second["created"] == 0
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert total == 3


def test_commit_handles_concurrent_partial_progress(db):
    """If another tab inserted 2 rows between preview and commit,
    the commit must insert only the remainder (1)."""
    row = _vespa_row(import_qty=3)
    row["preview_local_qty"] = 0

    # Simulate a concurrent tab inserting 2 rows before we commit.
    make_set(brand="LEGO", set_number="10298")
    make_set(brand="LEGO", set_number="10298")

    result = commit_import_rows([row])

    assert result["created"] == 1  # 3 desired - 2 already there = 1 new
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert total == 3


def test_commit_treats_missing_preview_local_qty_as_zero(db):
    """Defensive: a payload lacking preview_local_qty must not regress
    the happy-path insert count (treated as 0 = a fresh import)."""
    row = _vespa_row(import_qty=2)
    # Note: no preview_local_qty key set.
    result = commit_import_rows([row])
    assert result["created"] == 2
```

Now amend the existing test that asserts `created == 2` with `2` pre-existing rows; under the new semantics that test would over-count without `preview_local_qty`. Update `test_inserts_and_backfills_together`:

```python
def test_inserts_and_backfills_together(db):
    a = make_set(brand="LEGO", set_number="10298")
    b = make_set(brand="LEGO", set_number="10298")
    row = _vespa_row(
        import_qty=2,
        local_ids_missing_bs_id=[a, b],
    )
    # Preview saw 2 local rows; commit is asked to add 2 more (target = 4).
    row["preview_local_qty"] = 2
    result = commit_import_rows([row])
    assert result["created"] == 2
    assert result["backfilled"] == 2
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert total == 4  # 2 existing + 2 newly inserted
```

- [ ] **Step 2: Run the tests to verify they fail (the new ones) and the amended one still asserts 4**

```bash
pytest tests/test_commit_import_rows.py -v
```

Expected:
- `test_commit_is_idempotent_on_double_submit` — FAIL (second call still inserts 3).
- `test_commit_handles_concurrent_partial_progress` — FAIL.
- `test_commit_treats_missing_preview_local_qty_as_zero` — PASS today, must stay PASS.
- `test_inserts_and_backfills_together` (amended) — PASS today (still trivially inserts the full requested 2).

- [ ] **Step 3: Implement the idempotency in `commit_import_rows`**

Edit `navigation/set_manager.py` — replace the body of `commit_import_rows`:

```python
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
```

Note: `count_owned()` could be used instead of the inline `SELECT COUNT(*)`, but reusing the open connection avoids opening a second one mid-transaction. The condition matches `count_owned`'s `status='complete'` filter exactly.

- [ ] **Step 4: Add `preview_local_qty` to the route's preview payload**

Edit `main.py` inside `api_import_fetch` — extend the `payload` dict (from Task 1):

```python
        payload = {
            "brand":           brand,
            "set_number":      set_number,
            "name":            s.get("name") or "",
            "part_count":      s.get("pieces"),
            "theme":           s.get("theme"),
            "release_year":    s.get("year"),
            "ean":             s.get("ean"),
            "web_images":      [s["image_url"]] if s.get("image_url") else [],
            "brickset_set_id": s["set_id"],
            "local_ids_missing_bs_id": missing_ids,
            "preview_local_qty": local_qty,
        }
```

And carry it through the commit-route sanitisation (`main.py:api_import_commit`):

```python
        sanitised.append({
            "brand":                   str(row["brand"]),
            "set_number":              str(row["set_number"]),
            "name":                    row.get("name") or "",
            "part_count":              part_count,
            "theme":                   row.get("theme"),
            "release_year":            row.get("release_year"),
            "ean":                     row.get("ean"),
            "web_images":              row.get("web_images") or [],
            "brickset_set_id":         int(row["brickset_set_id"]),
            "import_qty":              qty,
            "local_ids_missing_bs_id": missing_ids,
            "preview_local_qty":       max(0, int(row.get("preview_local_qty") or 0)),
        })
```

(The client-supplied `preview_local_qty` is what the user saw at preview time. Trusting it for purposes of capping inserts is fine — the worst-case tampering is "user lies that they had 0 locally" → server attempts to insert N → `count_owned` shows N already, the new safety still caps real inserts to ≥0. Even with tampered=0 and current=N, `actual_insert = max(0, N - max(0, N - 0)) = max(0, N - N) = 0` ✓ )

Wait — recheck that. With tampered `preview_local_qty=0` and `current_local_count=N` and `import_qty=N`:
- `delta_already_imported = max(0, N - 0) = N`
- `actual_insert = max(0, N - N) = 0`

Good — tampering down to 0 makes the commit a no-op (over-counts the "already imported"). Tampering up doesn't help an attacker either. Safe.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/test_commit_import_rows.py tests/test_import_routes.py -v
```

Expected: All pass (including the previously-failing F3 tests, the F2 test from Task 3, and the amended `test_inserts_and_backfills_together`).

- [ ] **Step 6: Run the full suite**

```bash
pytest -q
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add main.py navigation/set_manager.py tests/test_commit_import_rows.py
git commit -m "fix(import): idempotent commit via preview_local_qty snapshot (F3)"
```

---

## Task 5: F5 — Validate `session_id` shape in `/api/upload`

A crafted `session_id` like `"../../etc/passwd"` would let an uploaded file land outside the staging directory. Add a strict regex check at the entry point; the frontend already uses `crypto.randomUUID()`, which passes.

**Files:**
- Test: `tests/test_api_upload.py` (new)
- Modify: `main.py` (`api_upload` and a module-level regex constant)

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_upload.py`:

```python
"""F5 — /api/upload must reject session_id values that aren't UUID-shaped."""
from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_rejects_path_traversal_session_id(db, tmp_path, monkeypatch):
    """A '../' in session_id must yield 400 and write no file outside staging."""
    from main import app
    from execution import photos as photos_module

    monkeypatch.setattr(photos_module, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "../../etc/passwd"},
        )

    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    # Nothing should have been written anywhere under tmp_path.
    written = list((tmp_path).rglob("*"))
    assert not any(p.is_file() for p in written)


def test_upload_accepts_uuid_shaped_session_id(db, tmp_path, monkeypatch):
    """A standard 36-char UUID session_id (matches crypto.randomUUID())
    must continue to succeed."""
    from main import app
    from execution import photos as photos_module

    monkeypatch.setattr(photos_module, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "550e8400-e29b-41d4-a716-446655440000"},
        )

    assert r.status_code == 200
    assert r.json()["ok"] is True
```

- [ ] **Step 2: Run the tests to verify failure**

```bash
pytest tests/test_api_upload.py -v
```

Expected: `test_upload_rejects_path_traversal_session_id` FAILS — the file is currently written under the traversed path (or at least an attempt is made; the response is 200 in any case).

- [ ] **Step 3: Add the regex and the guard**

Edit `main.py`. After the imports block (around line 23), add the module-level constant:

```python
import re

SESSION_ID_RE = re.compile(r"[a-fA-F0-9-]{8,64}")
```

Then modify `api_upload` (around line 415–419):

```python
@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), session_id: str = Form(...)):
    if not SESSION_ID_RE.fullmatch(session_id):
        return JSONResponse(
            {"ok": False, "error": "invalid session_id"},
            status_code=400,
        )
    content = await file.read()
    result  = upload_to_staging(content, file.filename or "photo", session_id)
    return JSONResponse(result)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_api_upload.py -v
```

Expected: Both PASS.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_api_upload.py
git commit -m "fix(upload): validate session_id shape to block path traversal (F5)"
```

---

## Task 6: S1 — Remove `uploads/{id}/` directory on `delete_set`

When a set is deleted, the DB row goes away but the photo directory lingers. Wire up `shutil.rmtree(UPLOADS_ROOT / str(set_id), ignore_errors=True)` after the DELETE.

**Files:**
- Test: `tests/test_set_manager_delete.py` (new)
- Modify: `navigation/set_manager.py` (`delete_set` and a new module-level constant or reuse of `execution.photos.UPLOADS_ROOT`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_set_manager_delete.py`:

```python
"""S1 — delete_set must remove the on-disk uploads/{id}/ folder."""
import shutil
from pathlib import Path

from execution.db import get_connection
from navigation.set_manager import delete_set
from tests.factories import make_set


def test_delete_set_removes_uploads_directory(db, tmp_path, monkeypatch):
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")
    # set_manager imports UPLOADS_ROOT lazily inside delete_set, so patching
    # the source module is sufficient.

    set_id = make_set()
    own_dir = tmp_path / "uploads" / str(set_id)
    own_dir.mkdir(parents=True)
    (own_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    delete_set(set_id)

    assert not own_dir.exists()
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM sets WHERE id=?", (set_id,)).fetchone()
    assert row is None


def test_delete_set_without_uploads_directory_is_silent(db, tmp_path, monkeypatch):
    """If the set has no uploaded photos (no folder), delete must still succeed."""
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    set_id = make_set()  # No uploads/{id}/ folder.
    delete_set(set_id)   # Must not raise.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM sets WHERE id=?", (set_id,)).fetchone()
    assert row is None
```

- [ ] **Step 2: Run the tests to verify failure**

```bash
pytest tests/test_set_manager_delete.py -v
```

Expected: First test FAILS (`own_dir` still exists). Second test passes today (no folder to delete, no crash).

- [ ] **Step 3: Implement the cleanup**

Edit `navigation/set_manager.py`. Add an import at the top (after the existing imports):

```python
import shutil
```

Then update `delete_set` (line 203–206):

```python
def delete_set(set_id: int) -> None:
    """Delete a set record and its uploads/{id}/ photo folder.
    Caller must have confirmed with user first.
    """
    from execution.photos import UPLOADS_ROOT
    with get_connection() as conn:
        conn.execute("DELETE FROM sets WHERE id=?", (set_id,))
    shutil.rmtree(UPLOADS_ROOT / str(set_id), ignore_errors=True)
```

The `from execution.photos import UPLOADS_ROOT` is inside the function deliberately so monkeypatching `photos_module.UPLOADS_ROOT` in tests works (Python re-resolves the import on every call). If a future maintainer hoists it, the test would need to patch `navigation.set_manager.UPLOADS_ROOT` instead — note this in a one-line comment.

Updated:

```python
def delete_set(set_id: int) -> None:
    """Delete a set record and its uploads/{id}/ photo folder.
    Caller must have confirmed with user first.
    """
    # NOTE: lazy import so tests can monkeypatch execution.photos.UPLOADS_ROOT.
    from execution.photos import UPLOADS_ROOT
    with get_connection() as conn:
        conn.execute("DELETE FROM sets WHERE id=?", (set_id,))
    shutil.rmtree(UPLOADS_ROOT / str(set_id), ignore_errors=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_set_manager_delete.py -v
```

Expected: Both PASS.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add navigation/set_manager.py tests/test_set_manager_delete.py
git commit -m "fix(sets): remove uploads/{id}/ folder when set is deleted (S1)"
```

---

## Task 7: S2 — Unlink removed photos on `update_set`

When the user removes a photo on the edit page, the file currently stays on disk forever. Compute the removed set and unlink each file before issuing the UPDATE.

**Files:**
- Test: `tests/test_set_manager_update.py` (new)
- Modify: `navigation/set_manager.py:update_set`

- [ ] **Step 1: Write the failing test**

Create `tests/test_set_manager_update.py`:

```python
"""S2 — update_set must unlink files that the user removed from own_photos."""
import json
from pathlib import Path

from execution.db import get_connection
from navigation.set_manager import update_set
from tests.factories import make_set


def test_update_set_unlinks_removed_photos(db, tmp_path, monkeypatch):
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    set_id = make_set()
    # Two pre-existing photos on disk + in DB.
    own_dir = tmp_path / "uploads" / str(set_id)
    own_dir.mkdir(parents=True)
    keep_path = f"uploads/{set_id}/keep.jpg"
    drop_path = f"uploads/{set_id}/drop.jpg"
    (tmp_path / keep_path).write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / drop_path).write_bytes(b"\xff\xd8\xff\xd9")
    with get_connection() as conn:
        conn.execute(
            "UPDATE sets SET own_photos=? WHERE id=?",
            (json.dumps([keep_path, drop_path]), set_id),
        )

    # User edits the set, removing `drop.jpg` (sends only `keep.jpg`).
    update_set(set_id, {
        "brand": "LEGO", "set_number": "0000", "name": "Test Set", "part_count": 100,
        "existing_own_photos": json.dumps([keep_path]),
    })

    assert (tmp_path / keep_path).exists()
    assert not (tmp_path / drop_path).exists()


def test_update_set_tolerates_already_missing_files(db, tmp_path, monkeypatch):
    """If a file the DB still lists is already gone from disk, update must not raise."""
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    set_id = make_set()
    ghost_path = f"uploads/{set_id}/ghost.jpg"
    with get_connection() as conn:
        conn.execute(
            "UPDATE sets SET own_photos=? WHERE id=?",
            (json.dumps([ghost_path]), set_id),
        )
    # No file on disk. User removes the entry — must not crash.
    update_set(set_id, {
        "brand": "LEGO", "set_number": "0000", "name": "Test Set", "part_count": 100,
        "existing_own_photos": json.dumps([]),
    })
```

- [ ] **Step 2: Run the tests to verify failure**

```bash
pytest tests/test_set_manager_update.py -v
```

Expected: First test FAILS — `drop.jpg` still on disk. Second test passes today (no unlink attempted).

- [ ] **Step 3: Implement the unlink-removed-photos logic**

Edit `navigation/set_manager.py:update_set`. Insert the cleanup block right after the `kept_photos = json.loads(...)` line:

```python
def update_set(set_id: int, data: dict, session_id: str | None = None) -> dict:
    """Update an existing set record. Keeps existing own_photos unless removed.
    Removed photos are unlinked from disk (S2)."""
    missing = [f for f in REQUIRED if not data.get(f)]
    status = "draft" if missing else "complete"

    kept_photos = json.loads(data.get("existing_own_photos") or "[]")

    # S2 — unlink photos the user removed from the edit form.
    # NOTE: lazy import so tests can monkeypatch execution.photos.UPLOADS_ROOT.
    from execution.photos import UPLOADS_ROOT
    from pathlib import Path
    with get_connection() as conn:
        old_row = conn.execute(
            "SELECT own_photos FROM sets WHERE id=?", (set_id,)
        ).fetchone()
    old_photos = json.loads(old_row["own_photos"] or "[]") if old_row else []
    removed = set(old_photos) - set(kept_photos)
    for rel in removed:
        try:
            # Paths in own_photos are relative to project root (e.g. "uploads/12/foo.jpg").
            # Strip the leading "uploads/" so we can resolve against UPLOADS_ROOT
            # (which itself ends in /uploads) without doubling the segment.
            stripped = rel[len("uploads/"):] if rel.startswith("uploads/") else rel
            (UPLOADS_ROOT / stripped).unlink(missing_ok=True)
        except OSError as exc:
            # Don't block the user's edit on a filesystem oddity (perms, race, etc.).
            import logging
            logging.getLogger(__name__).warning(
                "Could not unlink %s during edit cleanup: %s", rel, exc
            )

    with get_connection() as conn:
        conn.execute(
            ...  # existing UPDATE statement, unchanged
        )
    # ...rest of function unchanged
```

The path-stripping logic matters because `own_photos` stores paths like `"uploads/12/foo.jpg"` (relative to project root, as `finalise_photos` produces via `relative_to(Path("."))`), but `UPLOADS_ROOT` itself is `Path("uploads")`. Joining `UPLOADS_ROOT / "uploads/12/foo.jpg"` would yield `uploads/uploads/12/foo.jpg`, which is wrong. Strip the leading `uploads/` prefix first.

**Verify the path format yourself first** — read `execution/photos.py:finalise_photos:63` (`relative` is `dest.relative_to(Path("."))` → produces `uploads/{id}/{filename}`). Confirms the stripping is needed.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_set_manager_update.py -v
```

Expected: Both PASS.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add navigation/set_manager.py tests/test_set_manager_update.py
git commit -m "fix(sets): unlink removed photos on edit (S2)"
```

---

## Task 8: S3 — Populate `prefill["duplicates"]` so the add-page callout fires

The add page already has a `<div id="duplicate-callout">` and a `showDuplicateWarning(dupes)` JS function that the lookup handler calls when `data.prefill.duplicates && data.prefill.duplicates.length` is truthy. Today the route never sets that key. Wire it up in `_flow1` so the callout appears whenever a known set is already in the user's collection. Also switch the JS to use the existing i18n key (`errors.duplicate_warning`) instead of its hardcoded German/English strings.

**Files:**
- Test: `tests/test_lookup_router_duplicates.py` (new)
- Modify: `navigation/lookup_router.py:_flow1`
- Modify: `templates/add.html` (JS `showDuplicateWarning`)
- (No locale changes — `errors.duplicate_warning` already exists in both locales.)

- [ ] **Step 1: Write the failing test**

Create `tests/test_lookup_router_duplicates.py`:

```python
"""S3 — route_lookup must surface a duplicates count when the user already
owns this brand+set_number, so the add page can warn them."""
import pytest
from unittest.mock import AsyncMock, patch

from tests.factories import make_set


@pytest.mark.asyncio
async def test_duplicates_populated_when_set_already_owned(db):
    from navigation.lookup_router import route_lookup
    make_set(brand="LEGO", set_number="10298")
    make_set(brand="LEGO", set_number="10298")

    fake_scrape  = AsyncMock(return_value={"status": "success", "name": "Vespa"})
    fake_fetch   = AsyncMock(return_value={"status": "not_found"})

    with patch("navigation.lookup_router.scrape_set",  new=fake_scrape), \
         patch("navigation.lookup_router.fetch_set",   new=fake_fetch):
        result = await route_lookup(brand="LEGO", set_number="10298")

    assert result["status"] == "success"
    dupes = result["prefill"].get("duplicates") or []
    assert len(dupes) == 2


@pytest.mark.asyncio
async def test_duplicates_absent_when_set_not_owned(db):
    from navigation.lookup_router import route_lookup
    # No make_set() calls — collection is empty.
    fake_scrape  = AsyncMock(return_value={"status": "success", "name": "Vespa"})
    fake_fetch   = AsyncMock(return_value={"status": "not_found"})

    with patch("navigation.lookup_router.scrape_set",  new=fake_scrape), \
         patch("navigation.lookup_router.fetch_set",   new=fake_fetch):
        result = await route_lookup(brand="LEGO", set_number="10298")

    assert result["status"] == "success"
    assert not result["prefill"].get("duplicates")
```

`pytest.ini` has `asyncio_mode = auto` already (verified — async tests just need to be declared `async def`; the `@pytest.mark.asyncio` decorator is redundant but harmless).

- [ ] **Step 2: Run the tests to verify failure**

```bash
pytest tests/test_lookup_router_duplicates.py -v
```

Expected: First test FAILS — `prefill["duplicates"]` is missing.

- [ ] **Step 3: Populate duplicates in `_flow1`**

Edit `navigation/lookup_router.py`. Add import at the top:

```python
from navigation.set_manager import _find_duplicates
```

(`_find_duplicates` already exists in `set_manager.py:354-364` and returns a list of dicts including id/condition/note/date_of_purchase/status — exactly what a UI callout might want to render.)

Then inside `_flow1`, after the `prefill: dict = {"brand": brand, "set_number": set_number}` line (around line 74), add:

```python
    duplicates = _find_duplicates(brand, set_number)
    if duplicates:
        prefill["duplicates"] = duplicates
```

It belongs before the merlinssteine scrape, so the duplicates field rides along regardless of whether the scrape succeeds or not.

- [ ] **Step 4: Localise the JS callout text**

Edit `templates/add.html` — replace `showDuplicateWarning` (around line 326–335):

```javascript
function showDuplicateWarning(dupes) {
  const callout = document.getElementById('duplicate-callout');
  const text    = document.getElementById('duplicate-text');
  const tpl     = {{ t('errors.duplicate_warning', count='__N__') | tojson }};
  text.textContent = tpl.replace('__N__', dupes.length);
  callout.classList.remove('hidden');
}
```

The `{{ t(...) }}` is rendered at template-time, so the placeholder `__N__` ends up baked into the JS string with the user's current locale. Same `__N__` trick the import-button label uses (see `templates/import_brickset.html:33`).

- [ ] **Step 5: Run the tests to verify the route side passes**

```bash
pytest tests/test_lookup_router_duplicates.py -v
```

Expected: Both PASS.

- [ ] **Step 6: Manual smoke (no automated test for the JS)**

Start the dev server:

```bash
uvicorn main:app --reload --port 8000 &
```

Open `http://localhost:8000/add` in a browser. In another tab, add a LEGO set with brand=`LEGO` and set_number=`10298`. Save. Go back to `/add`, enter brand=`LEGO`, set_number=`10298`, click "Daten abrufen". Expected: yellow "Achtung" callout appears with the existing-count text from the locale. Kill the server (`fg`, then `Ctrl-C`) or `pkill -f "uvicorn main:app"`.

- [ ] **Step 7: Run the full suite**

```bash
pytest -q
```

Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add navigation/lookup_router.py templates/add.html tests/test_lookup_router_duplicates.py
git commit -m "fix(add): surface duplicate-warning callout on lookup (S3)"
```

---

## Task 9: S4 — Preserve `bs_qty=0` in the import preview

`bs_qty = s.get("qty_owned") or 1` flips a legitimate `0` to `1`. Use an explicit `is not None` check.

**Files:**
- Test: `tests/test_import_routes.py` (append)
- Modify: `main.py:164` (the `bs_qty` line in `api_import_fetch`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_import_routes.py`:

```python
def test_preview_preserves_bs_qty_zero(db):
    """S4 — Brickset's qtyOwned: 0 must come through as bs_qty=0,
    not get coerced to 1 by `or 1`."""
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch
    from main import app

    fake = {
        "status": "ok",
        "sets": [{
            "set_number": "10298",
            "set_id":     23456,
            "name":       "Vespa 125",
            "pieces":     1106,
            "theme":      "Creator Expert",
            "year":       2022,
            "ean":        None,
            "image_url":  None,
            "qty_owned":  0,  # The case under test.
        }],
    }
    with patch("execution.brickset.fetch_owned_collection",
               new=AsyncMock(return_value=fake)):
        with TestClient(app) as client:
            r = client.post("/api/import/brickset/fetch")

    assert r.status_code == 200
    # The summary chip carries machine-readable totals as data-* attrs.
    # bs_qty=0 ⇒ default_import_qty = max(0, 0 - 0) = 0 ⇒ will_create=0.
    assert 'data-will-create="0"' in r.text
    # The per-row qty label embeds bs_qty inside <strong>…</strong>.
    assert '<strong>0</strong>' in r.text
    # And the preview_local_qty snapshot must be 0 (no local rows exist).
    assert '"preview_local_qty": 0' in r.text
```

The "strong assertion" line is template-dependent — read `templates/_brickset_import_preview.html` lines 1–55 to find the totals/badge markup and assert against it. If the totals are exposed as `data-will-create="..."` attributes, grep for that. Otherwise, fall back to: the new code path must NOT produce `default_import_qty=1` when bs_qty came in as 0. Encode that as:

```python
    # default_import_qty = max(0, bs_qty - local_qty) = max(0, 0 - 0) = 0
    # So the totals.will_create must be 0.
    # Search for the rendered totals badge — the template uses
    # {{ totals.will_create }} which renders as a bare integer.
    assert "will_create" not in r.text  # sanity: it's a context key, not literal
    # Replace this with a real assertion once you've read the template:
    # e.g. assert 'data-will-create="0"' in r.text
```

(The implementer should read the template once and write the strongest possible assertion. The intent — `bs_qty=0` survives end-to-end — is the contract.)

- [ ] **Step 2: Run the test to verify failure**

```bash
pytest tests/test_import_routes.py::test_preview_preserves_bs_qty_zero -v
```

Expected: FAIL (today `bs_qty` becomes 1, `default_import_qty` becomes 1, the rendered totals reflect 1).

- [ ] **Step 3: Fix the coercion**

Edit `main.py:164`:

```python
        # before
        bs_qty = s.get("qty_owned") or 1
        # after
        bs_qty = s["qty_owned"] if s.get("qty_owned") is not None else 1
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_import_routes.py::test_preview_preserves_bs_qty_zero -v
```

Expected: PASS.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_import_routes.py
git commit -m "fix(import): preserve bs_qty=0 in preview (S4)"
```

---

## Task 10: S5 — Surface EAN-lookup status callouts on the edit page

The add page already shows callouts for `not_found`, `ean_unresolved`, `rate_limit`, and `error`. The edit page silently swallows them.

**Files:**
- Modify: `templates/edit.html` (the `doLookup` JS function)

No new test — this is JS-only, parallel to `add.html`'s existing behaviour. Manual smoke covers it.

- [ ] **Step 1: Mirror the status-handling block from `add.html`**

Edit `templates/edit.html:doLookup` (around line 209–234). The full new function:

```javascript
async function doLookup() {
  const ean   = document.getElementById('ean-input').value.trim();
  const brand = document.getElementById('brand-input').value.trim();
  const num   = document.getElementById('setnumber-input').value.trim();
  if (!ean && !brand && !num) return;

  const btn = document.getElementById('lookup-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  const body = new FormData();
  if (ean)   body.append('ean', ean);
  if (brand) body.append('brand', brand);
  if (num)   body.append('set_number', num);

  const r    = await fetch('/api/lookup', { method: 'POST', body });
  const data = await r.json();

  btn.disabled = false;
  lucide.createIcons();
  btn.innerHTML = '<i data-lucide="search" style="width:15px;height:15px"></i> '
    + (document.documentElement.lang === 'de' ? 'Daten abrufen' : 'Fetch Data');
  lucide.createIcons();

  applyPrefill(data.prefill || {});

  if (data.status === 'rate_limit' || data.status === 'not_found' || data.status === 'error') {
    showCallout(data.message, 'warn');
  } else if (data.status === 'ean_unresolved') {
    showCallout(data.message, 'info');
  }
}

// ── Callout (mirrors add.html) ───────────────────────────────────────────
function showCallout(msg, type) {
  let el = document.getElementById('dynamic-callout');
  if (!el) {
    el = document.createElement('div');
    el.id = 'dynamic-callout';
    document.getElementById('set-form').before(el);
  }
  const typeMap = { warn: 'Achtung', info: 'Hinweis', error: 'Fehler', ok: 'Klappt' };
  el.className = `callout callout-${type}`;
  el.innerHTML = `<span class="callout__mark">${typeMap[type] || 'Hinweis'}</span><p>${msg}</p>`;
}
```

Add the `showCallout` function below `doLookup` (or wherever the next blank-line break naturally falls in the file). It's identical to the add-page version — duplication is acceptable here since both templates are standalone documents and there's no shared JS file pattern in the project.

- [ ] **Step 2: Manual smoke**

Start the dev server:

```bash
uvicorn main:app --reload --port 8000 &
```

Open the edit page for any set (`http://localhost:8000/sets/1/edit`). Type a known-bad EAN like `9999999999999` and click "Daten abrufen". Expected: a `callout callout-info` appears above the form with the "EAN nicht erkannt..." message. Kill the server.

- [ ] **Step 3: Run the full suite**

```bash
pytest -q
```

Expected: All pass (no test added for S5; this just confirms nothing else broke).

- [ ] **Step 4: Commit**

```bash
git add templates/edit.html
git commit -m "fix(edit): surface EAN-lookup status callouts (S5)"
```

---

## Final Verification

- [ ] **Step 1: Run the entire test suite one last time**

```bash
pytest -q
```

Expected: All ~143 tests pass (133 existing + ~10 new).

- [ ] **Step 2: Skim the diff against `d2b7b1f` (the pre-iteration baseline)**

```bash
git diff --stat d2b7b1f..HEAD
```

Confirm all 10 fixes are represented across the files listed in the File Structure table above.

- [ ] **Step 3: Update the task plan**

Mark Iteration 4.6 complete in `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md` (add a line under the "Road to V1" section: `**Iteration 4.6** — code-review fixes (F1–F5, S1–S5) **✅ COMPLETE 2026-05-17**`).

- [ ] **Step 4: Note that Phase T is the only remaining V1 work**

Done. The next iteration is Phase T (LaunchAgent deployment) → V1 ships.
