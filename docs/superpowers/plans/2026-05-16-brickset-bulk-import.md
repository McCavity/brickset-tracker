# Brickset Bulk Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull the user's owned LEGO sets from Brickset into the local SQLite collection, with duplicate-aware semantics (multi-copy support) and a preview-then-commit UI.

**Architecture:** Three new server routes (`GET /import/brickset` page, `POST /api/import/brickset/fetch` returning an HTML preview partial, `POST /api/import/brickset/commit` accepting a JSON payload and inserting/backfilling rows). The Brickset client gains a paginated `fetch_owned_collection()`. The set manager gains `commit_import_rows()` and `find_local_rows_missing_brickset_id()`. Form-tampering is accepted (single-user local app); server validates required fields and silently skips malformed rows.

**Tech Stack:** FastAPI 0.115, Starlette 0.46, Jinja2 3.1, SQLite (stdlib `sqlite3`), `httpx` for Brickset HTTP, pytest with `monkeypatch` for HTTP mocking.

**Spec:** `docs/superpowers/specs/2026-05-16-brickset-bulk-import-design.md`

---

## Phase 0 — Backend data helpers (TDD)

### Task 1: `find_local_rows_missing_brickset_id()`

**Files:**
- Modify: `navigation/set_manager.py` (append a new function)
- Create: `tests/test_find_local_rows_missing_brickset_id.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_find_local_rows_missing_brickset_id.py`:
```python
"""find_local_rows_missing_brickset_id returns the ids of local rows that
match a brand+set_number AND have NULL brickset_set_id. These are the rows
the import will backfill."""
from navigation.set_manager import find_local_rows_missing_brickset_id
from tests.factories import make_set


def test_returns_empty_when_no_matching_rows(db):
    make_set(brand="LEGO", set_number="00000")
    assert find_local_rows_missing_brickset_id("LEGO", "99999") == []


def test_returns_ids_for_rows_with_null_brickset_id(db):
    a = make_set(brand="LEGO", set_number="42171")
    b = make_set(brand="LEGO", set_number="42171")
    ids = find_local_rows_missing_brickset_id("LEGO", "42171")
    assert sorted(ids) == sorted([a, b])


def test_excludes_rows_with_existing_brickset_id(db):
    a = make_set(brand="LEGO", set_number="42171")  # NULL bs_id
    b = make_set(brand="LEGO", set_number="42171")  # will get bs_id below
    from execution.db import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=99 WHERE id=?", (b,))
    ids = find_local_rows_missing_brickset_id("LEGO", "42171")
    assert ids == [a]


def test_brand_match_is_case_sensitive(db):
    # Existing get_sets is case-insensitive via py_lower; the BACKFILL helper
    # uses exact match because import always passes "LEGO" (Brickset is LEGO-only)
    make_set(brand="LEGO", set_number="42171")
    assert find_local_rows_missing_brickset_id("lego", "42171") == []
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_find_local_rows_missing_brickset_id.py -v`
Expected: ImportError / AttributeError on `find_local_rows_missing_brickset_id`.

- [ ] **Step 3: Implement in `navigation/set_manager.py`**

Append this function next to `count_owned()`:

```python
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
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_find_local_rows_missing_brickset_id.py -v`
Expected: 4 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 54 passed (50 prior + 4 new).

- [ ] **Step 5: Commit**

```
git add navigation/set_manager.py tests/test_find_local_rows_missing_brickset_id.py
git commit -m "feat(sets): add find_local_rows_missing_brickset_id helper

Used by the upcoming Brickset import to backfill brickset_set_id
on rows entered before Brickset had the set indexed."
```

---

### Task 2: `commit_import_rows()`

**Files:**
- Modify: `navigation/set_manager.py`
- Create: `tests/test_commit_import_rows.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_commit_import_rows.py`:
```python
"""commit_import_rows performs two operations per row:
  1. Backfill brickset_set_id on existing local rows in local_ids_missing_bs_id.
  2. Insert import_qty new rows with the Brickset metadata.
Both are independent — a row can have import_qty=0 (just backfill) or empty
local_ids_missing_bs_id (just insert)."""
from execution.db import get_connection
from navigation.set_manager import commit_import_rows
from tests.factories import make_set


def _vespa_row(import_qty=1, local_ids_missing_bs_id=None):
    return {
        "brand":           "LEGO",
        "set_number":      "10298",
        "name":            "Vespa 125",
        "part_count":      1106,
        "theme":           "Creator Expert",
        "release_year":    2022,
        "ean":             "5702016912661",
        "web_images":      ["https://images.brickset.com/sets/large/10298-1.jpg"],
        "brickset_set_id": 23456,
        "import_qty":      import_qty,
        "local_ids_missing_bs_id": local_ids_missing_bs_id or [],
    }


def test_inserts_new_rows(db):
    result = commit_import_rows([_vespa_row(import_qty=3)])
    assert result["created"] == 3
    assert result["backfilled"] == 0
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchall()
    assert len(rows) == 3
    for row in rows:
        assert row["name"] == "Vespa 125"
        assert row["part_count"] == 1106
        assert row["theme"] == "Creator Expert"
        assert row["release_year"] == 2022
        assert row["ean"] == "5702016912661"
        assert row["brickset_set_id"] == 23456
        assert row["status"] == "complete"
        assert "Imported from Brickset" in (row["note"] or "")


def test_backfills_existing_rows(db):
    existing = make_set(brand="LEGO", set_number="10298")
    result = commit_import_rows([_vespa_row(
        import_qty=0,
        local_ids_missing_bs_id=[existing],
    )])
    assert result["created"] == 0
    assert result["backfilled"] == 1
    with get_connection() as conn:
        row = conn.execute("SELECT brickset_set_id FROM sets WHERE id=?", (existing,)).fetchone()
    assert row["brickset_set_id"] == 23456


def test_inserts_and_backfills_together(db):
    a = make_set(brand="LEGO", set_number="10298")
    b = make_set(brand="LEGO", set_number="10298")
    result = commit_import_rows([_vespa_row(
        import_qty=2,
        local_ids_missing_bs_id=[a, b],
    )])
    assert result["created"] == 2
    assert result["backfilled"] == 2
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert total == 4  # 2 existing + 2 newly inserted


def test_zero_qty_zero_backfill_is_noop(db):
    result = commit_import_rows([_vespa_row(import_qty=0)])
    assert result == {"created": 0, "backfilled": 0}


def test_multiple_rows_in_one_call(db):
    rows = [
        _vespa_row(import_qty=1),
        {
            "brand":           "LEGO",
            "set_number":      "42171",
            "name":            "McLaren P1",
            "part_count":      3893,
            "theme":           "Technic",
            "release_year":    2023,
            "ean":             None,
            "web_images":      [],
            "brickset_set_id": 48541,
            "import_qty":      2,
            "local_ids_missing_bs_id": [],
        },
    ]
    result = commit_import_rows(rows)
    assert result == {"created": 3, "backfilled": 0}


def test_image_url_stored_in_web_images_json(db):
    commit_import_rows([_vespa_row(import_qty=1)])
    with get_connection() as conn:
        row = conn.execute("SELECT web_images FROM sets WHERE set_number='10298'").fetchone()
    import json
    images = json.loads(row["web_images"])
    assert images == ["https://images.brickset.com/sets/large/10298-1.jpg"]
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_commit_import_rows.py -v`
Expected: ImportError on `commit_import_rows`.

- [ ] **Step 3: Implement in `navigation/set_manager.py`**

Append this function (near `find_local_rows_missing_brickset_id`):

```python
def commit_import_rows(rows: list[dict]) -> dict:
    """Persist a batch of Brickset import rows.

    Each row dict has:
      brand, set_number, name, part_count, theme, release_year, ean,
      web_images (list of str), brickset_set_id (int),
      import_qty (int >= 0), local_ids_missing_bs_id (list[int]).

    For each row:
      - UPDATEs brickset_set_id on every id in local_ids_missing_bs_id.
      - INSERTs import_qty new rows with status='complete' and a note marking
        them as Brickset imports.

    Returns {"created": N, "backfilled": K} — total rows created/updated.
    """
    today = date.today().isoformat()
    note = f"Imported from Brickset on {today}"
    created = 0
    backfilled = 0

    with get_connection() as conn:
        for row in rows:
            # Backfill existing rows
            existing_ids = row.get("local_ids_missing_bs_id") or []
            if existing_ids:
                placeholders = ",".join("?" * len(existing_ids))
                cur = conn.execute(
                    f"""UPDATE sets SET brickset_set_id = ?, updated_at = datetime('now')
                        WHERE id IN ({placeholders})""",
                    (row["brickset_set_id"], *existing_ids),
                )
                backfilled += cur.rowcount

            # Insert new rows
            qty = int(row.get("import_qty") or 0)
            for _ in range(qty):
                conn.execute(
                    """INSERT INTO sets
                       (brand, set_number, name, part_count, theme, release_year,
                        ean, web_images, brickset_set_id, status, note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?)""",
                    (
                        row["brand"], row["set_number"], row["name"],
                        row.get("part_count"), row.get("theme"),
                        row.get("release_year"), row.get("ean"),
                        json.dumps(row.get("web_images") or []),
                        row["brickset_set_id"], note,
                    ),
                )
                created += 1

    return {"created": created, "backfilled": backfilled}
```

Note: `date` is already imported at the top of `set_manager.py` (`from datetime import date`); `json` is also already imported. No new imports needed.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_commit_import_rows.py -v`
Expected: 6 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 60 passed (54 prior + 6 new).

- [ ] **Step 5: Commit**

```
git add navigation/set_manager.py tests/test_commit_import_rows.py
git commit -m "feat(sets): add commit_import_rows for Brickset bulk import

Inserts import_qty new rows per Brickset set with status='complete'
and a marker note. Also backfills brickset_set_id on any existing
local rows for that brand+set_number that lacked it."
```

---

## Phase 1 — Brickset API client (TDD with HTTP mocks)

### Task 3: `_map_owned_set()` helper

**Files:**
- Modify: `execution/brickset.py` (append a helper next to `_map_set`)
- Create: `tests/test_map_owned_set.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_map_owned_set.py`:
```python
"""_map_owned_set extends _map_set with qtyOwned extraction from the
collection object Brickset returns on owned-flagged getSets calls."""
from execution.brickset import _map_owned_set


def test_extracts_qty_owned():
    raw = {
        "setID": 23456, "number": "10298", "name": "Vespa 125",
        "pieces": 1106, "theme": "Creator Expert", "year": 2022,
        "barcode": {"EAN": "5702016912661"},
        "image": {"imageURL": "https://example.com/v.jpg"},
        "collection": {"owned": True, "qtyOwned": 3},
    }
    r = _map_owned_set(raw)
    assert r["qty_owned"] == 3
    assert r["set_number"] == "10298"
    assert r["set_id"] == 23456
    assert r["name"] == "Vespa 125"
    assert r["pieces"] == 1106
    assert r["theme"] == "Creator Expert"
    assert r["year"] == 2022
    assert r["ean"] == "5702016912661"
    assert r["image_url"] == "https://example.com/v.jpg"


def test_defaults_qty_owned_to_one():
    """When the collection object is missing or qtyOwned is null."""
    raw = {"setID": 1, "number": "10298", "name": "X", "pieces": 1}
    assert _map_owned_set(raw)["qty_owned"] == 1

    raw_with_null = {**raw, "collection": {"qtyOwned": None}}
    assert _map_owned_set(raw_with_null)["qty_owned"] == 1

    raw_with_zero = {**raw, "collection": {"qtyOwned": 0}}
    # Zero is a valid response — respect it
    assert _map_owned_set(raw_with_zero)["qty_owned"] == 0


def test_uses_number_field_for_set_number():
    """Brickset's bare set number lives in the top-level 'number' field,
    not in setNumber (which it doesn't expose)."""
    raw = {"setID": 1, "number": "10298-1", "name": "X", "pieces": 1}
    r = _map_owned_set(raw)
    assert r["set_number"] == "10298-1"
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_map_owned_set.py -v`
Expected: ImportError on `_map_owned_set`.

- [ ] **Step 3: Implement in `execution/brickset.py`**

Append next to `_map_set`:

```python
def _map_owned_set(s: dict) -> dict:
    """Extension of _map_set that also extracts qtyOwned from the collection
    object Brickset returns when the request includes the user's userHash.

    The 'set_number' returned here is the bare/variant-suffixed number from
    Brickset's 'number' field — used for matching against local rows by
    brand+set_number.
    """
    base = _map_set(s)
    coll = s.get("collection") or {}
    qty  = coll.get("qtyOwned")
    base["qty_owned"]   = 1 if qty is None else qty
    base["set_number"]  = s.get("number")
    return base
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_map_owned_set.py -v`
Expected: 3 passed.

Full suite: 63 passed (60 + 3).

- [ ] **Step 5: Commit**

```
git add execution/brickset.py tests/test_map_owned_set.py
git commit -m "feat(brickset): add _map_owned_set helper for collection-aware mapping

Extracts qtyOwned from the collection object Brickset returns when
the request includes a userHash. Defaults to 1 if missing."
```

---

### Task 4: `fetch_owned_collection()` with pagination

**Files:**
- Modify: `execution/brickset.py` (append a new public function)
- Create: `tests/test_fetch_owned_collection.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fetch_owned_collection.py`:
```python
"""fetch_owned_collection pages through Brickset getSets with owned=1
until fewer than pageSize results return. Each page consumes one
quota point. Test by replacing httpx.AsyncClient with a fake that
serves a canned sequence of responses."""
import json

import httpx
import pytest

from execution import brickset, rate_limit
from execution.brickset import fetch_owned_collection


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def json(self):
        return self._payload


class _FakeClient:
    """Replaces httpx.AsyncClient. Dispenses canned responses in order
    and records each POST it received."""
    _pages: list = []
    calls:   list = []

    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def post(self, url, data):
        _FakeClient.calls.append({"url": url, "data": data})
        if not _FakeClient._pages:
            return _FakeResponse({"status": "success", "sets": []})
        return _FakeResponse(_FakeClient._pages.pop(0))


@pytest.fixture
def fake_brickset(monkeypatch, db):
    """Patch httpx.AsyncClient in execution.brickset to use _FakeClient.

    The db fixture is included so quota tracking writes to the temp DB.
    Use _FakeClient.set_pages([...]) before calling fetch_owned_collection.
    """
    _FakeClient._pages = []
    _FakeClient.calls = []
    monkeypatch.setattr(brickset.httpx, "AsyncClient", _FakeClient)
    yield _FakeClient


def _set(set_number: str) -> dict:
    return {
        "setID": int(set_number.replace("-", "")[:6]),
        "number": set_number, "name": f"Set {set_number}",
        "pieces": 100, "theme": "Test", "year": 2024,
        "barcode": {}, "image": {},
        "collection": {"qtyOwned": 1},
    }


def _page(sets, status="success"):
    return {"status": status, "sets": sets}


async def test_single_page_under_size(fake_brickset):
    """One page with 30 sets exits cleanly with a single API call."""
    fake_brickset._pages = [_page([_set(f"100{i:02d}") for i in range(30)])]
    result = await fetch_owned_collection()
    assert result["status"] == "ok"
    assert len(result["sets"]) == 30
    assert len(fake_brickset.calls) == 1


async def test_pages_through_multiple_pages(fake_brickset):
    """130 sets total → page 1 = 100, page 2 = 30, exits."""
    fake_brickset._pages = [
        _page([_set(f"100{i:02d}") for i in range(100)]),
        _page([_set(f"200{i:02d}") for i in range(30)]),
    ]
    result = await fetch_owned_collection()
    assert result["status"] == "ok"
    assert len(result["sets"]) == 130
    assert len(fake_brickset.calls) == 2


async def test_exact_multiple_of_page_size_makes_one_extra_call(fake_brickset):
    """Exactly 100 sets → page 1 = 100, page 2 = 0, exits.
    The empty page counts as one quota point (acceptable edge case)."""
    fake_brickset._pages = [
        _page([_set(f"100{i:02d}") for i in range(100)]),
        _page([]),
    ]
    result = await fetch_owned_collection()
    assert result["status"] == "ok"
    assert len(result["sets"]) == 100
    assert len(fake_brickset.calls) == 2


async def test_brickset_returns_non_success(fake_brickset):
    fake_brickset._pages = [{"status": "invalidApiKey", "message": "Bad key"}]
    result = await fetch_owned_collection()
    assert result["status"] == "error"
    assert "Bad key" in (result.get("message") or "")


async def test_quota_exceeded_blocks_first_call(monkeypatch, fake_brickset):
    monkeypatch.setattr("execution.brickset.check_quota", lambda svc: False)
    result = await fetch_owned_collection()
    assert result["status"] == "quota_exceeded"
    assert len(fake_brickset.calls) == 0


async def test_payload_includes_owned_and_user_hash(fake_brickset):
    fake_brickset._pages = [_page([])]
    await fetch_owned_collection()
    posted = fake_brickset.calls[0]["data"]
    params = json.loads(posted["params"])
    assert params.get("owned") == 1
    assert "userHash" in posted
    assert "apiKey" in posted
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_fetch_owned_collection.py -v`
Expected: ImportError on `fetch_owned_collection`.

- [ ] **Step 3: Implement in `execution/brickset.py`**

Append after the existing `sync_owned` function:

```python
PAGE_SIZE = 100


async def fetch_owned_collection() -> dict:
    """Return all LEGO sets the user owns on Brickset.

    Pages through getSets with owned=1 until fewer than PAGE_SIZE results
    return. Each page consumes one quota point. The "next page is empty"
    case (when the total is an exact multiple of PAGE_SIZE) costs one
    extra quota point — acceptable for V1.

    Returns:
        {"status": "ok", "sets": [...]}        on success
        {"status": "quota_exceeded"}           if quota is exhausted before any call
        {"status": "error", "message": "..."}  on network/API failure
    """
    all_sets: list[dict] = []
    page = 1

    while True:
        if not check_quota("brickset"):
            return {"status": "quota_exceeded"}

        params = json.dumps({
            "owned":      1,
            "pageSize":   PAGE_SIZE,
            "pageNumber": page,
        })
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(f"{BASE}/getSets", data={
                    "apiKey": API_KEY, "userHash": USER_HASH, "params": params,
                })
        except httpx.RequestError as e:
            log.warning("Brickset network error: %s", e)
            return {"status": "error", "message": str(e)}

        increment_quota("brickset")

        body = r.json()
        if body.get("status") != "success":
            return {"status": "error", "message": body.get("message")}

        page_sets = body.get("sets", [])
        all_sets.extend(_map_owned_set(s) for s in page_sets)

        if len(page_sets) < PAGE_SIZE:
            break
        page += 1

    return {"status": "ok", "sets": all_sets}
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_fetch_owned_collection.py -v`
Expected: 6 passed.

Full suite: 69 passed (63 + 6).

- [ ] **Step 5: Commit**

```
git add execution/brickset.py tests/test_fetch_owned_collection.py
git commit -m "feat(brickset): add fetch_owned_collection with auto-pagination

Pages through getSets with owned=1 + userHash until fewer than
PAGE_SIZE results return. One quota point per page. Tests use a
fake httpx.AsyncClient via monkeypatch to verify pagination and
error paths without hitting the live API."
```

---

## Phase 2 — Routes (TDD with TestClient)

### Task 5: `GET /import/brickset` page

**Files:**
- Modify: `main.py`
- Create: `templates/import_brickset.html` (minimal stub — fleshed out in Task 8)
- Create: `tests/test_import_routes.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_import_routes.py`:
```python
"""Smoke tests for the three Brickset import routes."""
from fastapi.testclient import TestClient
from main import app


def test_import_page_renders(db):
    client = TestClient(app)
    r = client.get("/import/brickset")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The fetch button must be on the page so the user can start
    assert 'id="fetch-button"' in r.text
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_import_routes.py -v`
Expected: 404.

- [ ] **Step 3: Create a minimal `templates/import_brickset.html`**

```html
{% extends "base.html" %}
{% block title %}{{ t('import.title') }} · Brickset Tracker{% endblock %}
{% block header_title %}{{ t('import.title') }}{% endblock %}

{% block content %}
<div class="page-header">
  <h1>{{ t('import.title') }}</h1>
  <a href="/" class="btn btn-ghost">
    <i data-lucide="x" style="width:15px;height:15px"></i>
    {{ t('add.cancel') }}
  </a>
</div>

<div id="import-initial">
  <p style="margin-bottom: var(--sp-4); color: var(--fg-muted)">
    {{ t('import.intro') }}
  </p>
  <button type="button" id="fetch-button" class="btn btn-primary">
    <i data-lucide="download" style="width:15px;height:15px"></i>
    {{ t('import.fetch_button') }}
  </button>
</div>

<div id="import-preview" class="hidden"></div>
{% endblock %}
```

This is the minimum needed for the test to pass. Task 8 fleshes out the JS and final styling.

- [ ] **Step 4: Add the route to `main.py`**

After the existing `/add` page route (around line 65), insert:

```python
@app.get("/import/brickset", response_class=HTMLResponse)
async def import_page(request: Request):
    return templates.TemplateResponse(request, "import_brickset.html", context=_ctx(request))
```

- [ ] **Step 5: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_import_routes.py -v`
Expected: 1 passed.

Full suite: 70 passed.

- [ ] **Step 6: Commit**

```
git add main.py templates/import_brickset.html tests/test_import_routes.py
git commit -m "feat(routes): add GET /import/brickset stub page

Minimum viable page with a fetch button. Subsequent tasks add the
preview rendering and JS interactivity."
```

---

### Task 6: `POST /api/import/brickset/fetch` returning preview partial

**Files:**
- Modify: `main.py` (add route)
- Create: `templates/_brickset_import_preview.html` (preview table partial)
- Modify: `tests/test_import_routes.py` (add tests)

- [ ] **Step 1: Append failing tests to `tests/test_import_routes.py`**

```python
import pytest
from execution import brickset
from tests.test_fetch_owned_collection import _FakeClient, _set, _page


@pytest.fixture
def fake_brickset(monkeypatch, db):
    _FakeClient._pages = []
    _FakeClient.calls = []
    monkeypatch.setattr(brickset.httpx, "AsyncClient", _FakeClient)
    yield _FakeClient


def test_fetch_endpoint_returns_html_partial(fake_brickset):
    fake_brickset._pages = [_page([_set("10298"), _set("42171")])]
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # No page chrome — it's a partial
    assert "<html" not in r.text.lower()
    # Should mention both set numbers
    assert "10298" in r.text
    assert "42171" in r.text


def test_fetch_endpoint_skips_malformed_sets(fake_brickset):
    """A Brickset response with a malformed set (missing number) must not crash."""
    valid = _set("10298")
    broken = {"setID": 1, "name": "broken"}  # no 'number'
    fake_brickset._pages = [_page([valid, broken])]
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    assert r.status_code == 200
    assert "10298" in r.text
    # The broken set is silently skipped — page still renders


def test_fetch_endpoint_surfaces_quota_error(monkeypatch, fake_brickset):
    monkeypatch.setattr("execution.brickset.check_quota", lambda svc: False)
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    assert r.status_code == 200
    # The partial shows the user-facing quota message
    assert "quota" in r.text.lower() or "limit" in r.text.lower() or "Tageslimit" in r.text


def test_fetch_endpoint_computes_local_qty(fake_brickset):
    """When a Brickset set already exists locally, local_qty must reflect that
    so the row displays the right comparison."""
    from tests.factories import make_set
    # User already has 2 local copies of set 10298
    make_set(brand="LEGO", set_number="10298")
    make_set(brand="LEGO", set_number="10298")

    fake_brickset._pages = [_page([_set("10298")])]
    client = TestClient(app)
    r = client.post("/api/import/brickset/fetch")
    # The preview row should reflect local_qty=2 and bs_qty=1
    assert "10298" in r.text
    # 'Local: 2' or similar — depends on i18n. Just verify the count makes it in.
    assert "2" in r.text
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_import_routes.py -v`
Expected: 4 tests fail with 404 on the new endpoint.

- [ ] **Step 3: Create the preview partial template**

Write `templates/_brickset_import_preview.html`:

```html
{# Brickset import preview partial — returned by POST /api/import/brickset/fetch #}
<div id="import-preview-content">

  {% if fetch_status == "quota_exceeded" %}
    <div class="callout callout-warn">
      <span class="callout__mark">!</span>
      <p>{{ t('import.error_quota') }}</p>
    </div>

  {% elif fetch_status == "error" %}
    <div class="callout callout-error">
      <span class="callout__mark">×</span>
      <p>{{ t('import.error_fetch', message=fetch_message or '') }}</p>
    </div>

  {% elif not rows %}
    <div class="empty-state">
      <h2>{{ t('import.no_sets') }}</h2>
    </div>

  {% else %}
    <p class="import-summary" id="import-summary"
       data-total-rows="{{ rows | length }}"
       data-will-create="{{ totals.will_create }}"
       data-will-backfill="{{ totals.will_backfill }}">
      {{ t('import.summary',
            bs_total=totals.bs_total,
            will_create=totals.will_create,
            sets_count=totals.sets_count,
            will_backfill=totals.will_backfill) }}
    </p>

    <form id="import-form" onsubmit="return submitImport(event)">
      <div class="import-preview-list">
        {% for row in rows %}
        <div class="import-preview-row" data-row-index="{{ loop.index0 }}">
          <label class="import-preview-row__pick">
            <input type="checkbox" class="import-row-check" checked>
            <div>
              <div class="import-preview-row__kicker">
                LEGO · <span class="mono">{{ row.set_number }}</span>
              </div>
              <div class="import-preview-row__name">{{ row.name }}</div>
              <div class="import-preview-row__meta">
                {% if row.theme %}<span>{{ row.theme }}</span>{% endif %}
                {% if row.release_year %}<span class="mono">{{ row.release_year }}</span>{% endif %}
                {% if row.part_count %}<span>{{ row.part_count }}</span>{% endif %}
              </div>
            </div>
          </label>

          <div class="import-preview-row__qty">
            <span>{{ t('import.col_bs_qty') }}: <strong>{{ row.bs_qty }}</strong></span>
            <span>{{ t('import.col_local_qty') }}: <strong>{{ row.local_qty }}</strong></span>
            <label>
              {{ t('import.col_import') }}:
              <input type="number" class="import-qty-input" min="0"
                     value="{{ row.default_import_qty }}">
            </label>
          </div>

          {% if row.hint_key %}
            <div class="import-preview-row__hint">
              {{ t(row.hint_key, diff=row.local_qty - row.bs_qty if row.local_qty > row.bs_qty else 0) }}
            </div>
          {% endif %}

          {# Hidden payload — server commits using these values #}
          <script type="application/json" class="import-row-payload">
            {{ row.payload_json | safe }}
          </script>
        </div>
        {% endfor %}
      </div>

      <div class="form-actions">
        <a href="/" class="btn btn-ghost">
          <i data-lucide="x" style="width:15px;height:15px"></i>
          {{ t('add.cancel') }}
        </a>
        <span class="spacer"></span>
        <button type="submit" class="btn btn-primary" id="import-submit">
          <i data-lucide="download" style="width:15px;height:15px"></i>
          <span id="import-submit-label">{{ t('import.submit_button', n=totals.will_create) }}</span>
        </button>
      </div>
    </form>
  {% endif %}

</div>
```

- [ ] **Step 4: Add the `api_import_fetch` route to `main.py`**

After the `import_page` route, append:

```python
@app.post("/api/import/brickset/fetch", response_class=HTMLResponse)
async def api_import_fetch(request: Request):
    """Fetch the user's Brickset collection and return a preview partial."""
    import json
    from execution.brickset import fetch_owned_collection
    from navigation.set_manager import count_owned, find_local_rows_missing_brickset_id

    result = await fetch_owned_collection()

    ctx = _ctx(request, fetch_status=result["status"])

    if result["status"] != "ok":
        ctx["fetch_message"] = result.get("message", "")
        ctx["rows"] = []
        ctx["totals"] = {"bs_total": 0, "will_create": 0, "sets_count": 0, "will_backfill": 0}
        return templates.TemplateResponse(request, "_brickset_import_preview.html", context=ctx)

    rows = []
    will_create = 0
    will_backfill = 0
    for s in result["sets"]:
        # Defensive: skip Brickset rows missing essential identifying fields
        if not s.get("set_number") or not s.get("set_id"):
            continue

        brand = "LEGO"
        set_number = s["set_number"]
        local_qty = count_owned(brand, set_number)
        missing_ids = find_local_rows_missing_brickset_id(brand, set_number)

        bs_qty = s.get("qty_owned") or 1
        default_import_qty = max(0, bs_qty - local_qty)
        will_create += default_import_qty
        will_backfill += len(missing_ids)

        if local_qty == 0:
            hint_key = None
        elif local_qty < bs_qty:
            hint_key = "import.hint_partial"
        elif local_qty == bs_qty:
            hint_key = "import.hint_already_covered"
        else:  # local_qty > bs_qty
            hint_key = "import.hint_local_richer"

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
            "payload_json":       json.dumps(payload),
        })

    ctx["rows"] = rows
    ctx["totals"] = {
        "bs_total":      sum(r["bs_qty"] for r in rows),
        "will_create":   will_create,
        "sets_count":    len([r for r in rows if r["default_import_qty"] > 0]),
        "will_backfill": will_backfill,
    }
    return templates.TemplateResponse(request, "_brickset_import_preview.html", context=ctx)
```

Notes:
- `import json` is done inside the function body (matching the existing `main.py` pattern where `api_save_set` does the same — keeps the top-level imports lean).
- The `import.no_sets` i18n key is added in Task 11; until then the empty-state branch will render the literal string `import.no_sets`. Acceptable for testing because the tests in this task don't exercise the empty-Brickset path.

- [ ] **Step 5: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_import_routes.py -v`
Expected: 5 passed (1 prior + 4 new).

Full suite: 75 passed.

- [ ] **Step 6: Commit**

```
git add main.py templates/_brickset_import_preview.html tests/test_import_routes.py
git commit -m "feat(routes): add POST /api/import/brickset/fetch returning preview partial

Computes per-row state (new / partial / already-covered / local-richer)
from Brickset response + count_owned + find_local_rows_missing_brickset_id.
Embeds the commit payload as inline JSON so the frontend can replay it
on submit without re-fetching from Brickset."
```

---

### Task 7: `POST /api/import/brickset/commit` route

**Files:**
- Modify: `main.py` (add route)
- Modify: `tests/test_import_routes.py` (add tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_import_routes.py`:

```python
def test_commit_inserts_and_redirects(db):
    """POST commit with a single row → inserts and redirects to /."""
    client = TestClient(app)
    payload = {
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
            "import_qty":      2,
            "local_ids_missing_bs_id": [],
        }],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/?imported=2&backfilled=0" in r.headers.get("location", "") \
        or "imported=2" in r.headers.get("location", "")

    # Verify the inserts
    from execution.db import get_connection
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM sets WHERE brand='LEGO' AND set_number='10298'"
        ).fetchone()["n"]
    assert count == 2


def test_commit_validates_required_fields(db):
    """Rows missing brand or set_number are silently skipped."""
    client = TestClient(app)
    payload = {
        "rows": [
            {"brand": "LEGO", "set_number": "", "import_qty": 1,
             "brickset_set_id": 1, "name": "X", "local_ids_missing_bs_id": []},
            {"brand": "LEGO", "set_number": "10298", "import_qty": 1,
             "brickset_set_id": 23456, "name": "Vespa", "local_ids_missing_bs_id": [],
             "web_images": []},
        ],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)

    from execution.db import get_connection
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM sets").fetchone()["n"]
    # Only the valid row was committed
    assert count == 1


def test_commit_validates_import_qty_is_non_negative(db):
    """import_qty < 0 is silently clamped to 0; row's backfill still runs."""
    client = TestClient(app)
    payload = {
        "rows": [{
            "brand": "LEGO", "set_number": "10298",
            "brickset_set_id": 23456, "name": "Vespa", "web_images": [],
            "import_qty": -5, "local_ids_missing_bs_id": [],
        }],
    }
    r = client.post("/api/import/brickset/commit", json=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    from execution.db import get_connection
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM sets").fetchone()["n"]
    assert count == 0


def test_commit_handles_empty_rows_list(db):
    client = TestClient(app)
    r = client.post("/api/import/brickset/commit", json={"rows": []}, follow_redirects=False)
    assert r.status_code in (302, 303)
    # Should redirect with 0/0 counts
    assert "imported=0" in r.headers.get("location", "")
    assert "backfilled=0" in r.headers.get("location", "")
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_import_routes.py -v`
Expected: 4 new tests fail with 404 / 405.

- [ ] **Step 3: Add the commit route to `main.py`**

Append after `api_import_fetch`:

```python
@app.post("/api/import/brickset/commit")
async def api_import_commit(request: Request):
    """Commit a Brickset import. Accepts JSON payload {"rows": [...]}.

    Each row must have: brand, set_number, brickset_set_id, name, import_qty
    (non-negative int), local_ids_missing_bs_id (list[int]).
    Optional: part_count, theme, release_year, ean, web_images (list).

    Returns a 303 redirect to /?imported=N&backfilled=K.
    """
    from navigation.set_manager import commit_import_rows

    body = await request.json()
    raw_rows = body.get("rows") or []

    sanitised = []
    for row in raw_rows:
        # Validate required fields
        if not row.get("brand") or not row.get("set_number"):
            continue
        if not row.get("brickset_set_id"):
            continue

        # Clamp import_qty to non-negative int
        try:
            qty = max(0, int(row.get("import_qty") or 0))
        except (TypeError, ValueError):
            qty = 0

        sanitised.append({
            "brand":                   str(row["brand"]),
            "set_number":              str(row["set_number"]),
            "name":                    row.get("name") or "",
            "part_count":              row.get("part_count"),
            "theme":                   row.get("theme"),
            "release_year":            row.get("release_year"),
            "ean":                     row.get("ean"),
            "web_images":              row.get("web_images") or [],
            "brickset_set_id":         int(row["brickset_set_id"]),
            "import_qty":              qty,
            "local_ids_missing_bs_id": [int(x) for x in (row.get("local_ids_missing_bs_id") or [])],
        })

    result = commit_import_rows(sanitised)
    return RedirectResponse(
        f"/?imported={result['created']}&backfilled={result['backfilled']}",
        status_code=303,
    )
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_import_routes.py -v`
Expected: 9 passed (5 prior + 4 new).

Full suite: 79 passed.

- [ ] **Step 5: Commit**

```
git add main.py tests/test_import_routes.py
git commit -m "feat(routes): add POST /api/import/brickset/commit

Accepts JSON {rows: [...]} with one entry per Brickset set, calls
commit_import_rows, redirects to /?imported=N&backfilled=K.
Validates each row's required fields (brand, set_number,
brickset_set_id) and clamps import_qty to non-negative int.
Invalid rows are silently skipped."
```

---

## Phase 3 — Templates and frontend JS (manual verification)

### Task 8: Add the JS to `templates/import_brickset.html`

**Files:**
- Modify: `templates/import_brickset.html`

- [ ] **Step 1: Replace the file with the full version**

Overwrite `templates/import_brickset.html`:

```html
{% extends "base.html" %}
{% block title %}{{ t('import.title') }} · Brickset Tracker{% endblock %}
{% block header_title %}{{ t('import.title') }}{% endblock %}

{% block content %}
<div class="page-header">
  <h1>{{ t('import.title') }}</h1>
  <a href="/" class="btn btn-ghost">
    <i data-lucide="x" style="width:15px;height:15px"></i>
    {{ t('add.cancel') }}
  </a>
</div>

<div id="import-initial">
  <p style="margin-bottom: var(--sp-4); color: var(--fg-muted)">
    {{ t('import.intro') }}
  </p>
  <button type="button" id="fetch-button" class="btn btn-primary">
    <i data-lucide="download" style="width:15px;height:15px"></i>
    <span id="fetch-button-label">{{ t('import.fetch_button') }}</span>
  </button>
</div>

<div id="import-preview" class="hidden"></div>
{% endblock %}

{% block scripts %}
<script>
const FETCH_BUTTON       = document.getElementById('fetch-button');
const FETCH_BUTTON_LABEL = document.getElementById('fetch-button-label');
const FETCH_LABEL_FETCH  = {{ t('import.fetch_button') | tojson }};
const FETCH_LABEL_BUSY   = {{ t('import.fetching') | tojson }};
const SUBMIT_LABEL_TPL   = {{ t('import.submit_button', n='__N__') | tojson }};

// ── Fetch the Brickset collection ────────────────────────────────────────
FETCH_BUTTON.addEventListener('click', async () => {
  FETCH_BUTTON.disabled = true;
  FETCH_BUTTON_LABEL.textContent = FETCH_LABEL_BUSY;
  try {
    const r = await fetch('/api/import/brickset/fetch', { method: 'POST' });
    if (!r.ok) throw new Error(`Server error ${r.status}`);
    const html = await r.text();

    document.getElementById('import-initial').classList.add('hidden');
    const host = document.getElementById('import-preview');
    host.innerHTML = html;
    host.classList.remove('hidden');
    lucide.createIcons();
    wirePreview();
  } catch (err) {
    FETCH_BUTTON.disabled = false;
    FETCH_BUTTON_LABEL.textContent = FETCH_LABEL_FETCH;
    alert('Fetch failed: ' + err.message);
  }
});

// ── Wire up the preview interactions ─────────────────────────────────────
function wirePreview() {
  const list   = document.querySelector('.import-preview-list');
  if (!list) return;

  function recompute() {
    let totalRows = 0;
    list.querySelectorAll('.import-preview-row').forEach(row => {
      const ticked = row.querySelector('.import-row-check').checked;
      const qty    = parseInt(row.querySelector('.import-qty-input').value, 10) || 0;
      if (ticked) totalRows += qty;
      row.style.opacity = ticked ? '' : '.45';
    });
    const label = document.getElementById('import-submit-label');
    if (label) label.textContent = SUBMIT_LABEL_TPL.replace('__N__', totalRows);
  }

  list.addEventListener('change', recompute);
  list.addEventListener('input',  recompute);
  recompute();
}

// ── Submit the import ────────────────────────────────────────────────────
async function submitImport(event) {
  event.preventDefault();
  const submit = document.getElementById('import-submit');
  submit.disabled = true;

  const rows = [];
  document.querySelectorAll('.import-preview-row').forEach(row => {
    const ticked = row.querySelector('.import-row-check').checked;
    if (!ticked) return;
    const qty = parseInt(row.querySelector('.import-qty-input').value, 10) || 0;
    const payload = JSON.parse(row.querySelector('.import-row-payload').textContent);
    payload.import_qty = qty;
    rows.push(payload);
  });

  try {
    const r = await fetch('/api/import/brickset/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    });
    if (r.redirected) {
      window.location.href = r.url;
    } else if (r.ok) {
      window.location.href = '/';
    } else {
      throw new Error(`Server error ${r.status}`);
    }
  } catch (err) {
    submit.disabled = false;
    alert('Import failed: ' + err.message);
  }
  return false;
}
</script>
{% endblock %}
```

- [ ] **Step 2: Verify pytest still passes**

Run: `.venv/bin/pytest -v`
Expected: 79 passed.

- [ ] **Step 3: Smoke test in the browser**

Start a temp uvicorn on port 8128 in the background:
```
.venv/bin/uvicorn main:app --port 8128
```

Then in a browser, open `http://localhost:8128/import/brickset`. Click "Fetch my Brickset collection". The preview table should load with a row per Brickset-owned set. Untick a row and confirm the submit-button label updates ("Import selected (N rows)"). Change a qty input and verify the same.

Kill the server when done: `pkill -f "port 8128"`.

(Don't commit imports yet — Task 9 adds the flash banner; Task 14 is full E2E.)

- [ ] **Step 4: Commit**

```
git add templates/import_brickset.html
git commit -m "feat(ui): wire up fetch and submit JS for Brickset import page

Fetch button retrieves the preview partial and swaps it into the DOM.
Submit button collects per-row payloads (including unchecked exclusions)
and POSTs them as JSON to the commit endpoint. Submit label updates
live as the user adjusts counts."
```

---

### Task 9: Flash banner on `/` after import

**Files:**
- Modify: `templates/index.html` (add the banner)
- Modify: `main.py` (pass query params into the route context)

- [ ] **Step 1: Modify the `/` route to read import flash params**

Open `main.py`, find the `index` function, and update its signature + body to accept optional `imported` and `backfilled` query params:

```python
@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    sort: str = "date_of_purchase",
    dir: str = "DESC",
    q: str | None = None,
    brand: list[str] = Query(default_factory=list),
    condition: list[str] = Query(default_factory=list),
    theme: list[str] = Query(default_factory=list),
    status: list[str] = Query(default_factory=list),
    imported: int | None = None,
    backfilled: int | None = None,
):
    q_clean = (q or "").strip()[:200] or None

    sets = get_sets(
        sort_by=sort, sort_dir=dir, q=q_clean,
        brands=brand, conditions=condition,
        themes=theme, statuses=status,
    )
    facets = get_facet_counts(
        q=q_clean, brands=brand, conditions=condition,
        themes=theme, statuses=status,
    )
    total = count_all_sets()

    return templates.TemplateResponse(request, "index.html", context=_ctx(
        request, sets=sets, facets=facets, total=total,
        active_filters={"brand": brand, "condition": condition,
                        "theme": theme, "status": status},
        q=q_clean or "", sort=sort, dir=dir,
        sort_options=["date_of_purchase", "name", "brand", "part_count", "price_paid"],
        flash_imported=imported,
        flash_backfilled=backfilled,
    ))
```

- [ ] **Step 2: Add the flash banner to `templates/index.html`**

Open `templates/index.html`. Find the `<div class="page-header">` element near the top of the `{% block content %}`. Insert this BEFORE it:

```html
{% if flash_imported is not none and flash_backfilled is not none %}
<div class="callout callout-ok flash-banner">
  <span class="callout__mark">✓</span>
  <p>{{ t('import.flash_success', created=flash_imported, backfilled=flash_backfilled) }}</p>
</div>
{% endif %}
```

- [ ] **Step 3: Verify**

Run: `.venv/bin/pytest -v`
Expected: 79 passed.

Browser smoke: open `http://localhost:8128/?imported=3&backfilled=1` — the green banner appears at the top.

- [ ] **Step 4: Commit**

```
git add main.py templates/index.html
git commit -m "feat(ui): flash banner on / after Brickset import

Reads ?imported=N&backfilled=K query params on the index route and
renders a confirmation banner above the page header."
```

---

### Task 10: Add the "Import from Brickset" link to the page header

**Files:**
- Modify: `templates/index.html` (extend the page-header div)

- [ ] **Step 1: Replace the page-header markup**

In `templates/index.html`, locate this block in `{% block content %}`:

```html
<div class="page-header">
  <div style="display:flex;align-items:center;gap:16px">
    <h1>{{ t('list.title') }}</h1>
    {% set ms = quota.merlinssteine %}
    <span class="quota-badge{% if ms.remaining == 0 %} exhausted{% endif %}">
      {{ t('quota.remaining', remaining=ms.remaining, limit=ms.limit) }}
    </span>
  </div>
  <a href="/add" class="btn btn-primary">
    <i data-lucide="plus" style="width:15px;height:15px"></i>
    {{ t('add.title') }}
  </a>
</div>
```

Replace the trailing `<a href="/add" ...>` block with:

```html
  <div style="display:flex;align-items:center;gap:var(--sp-3)">
    {% if quota.brickset.remaining > 0 %}
    <a href="/import/brickset" class="btn btn-ghost">
      <i data-lucide="download" style="width:15px;height:15px"></i>
      {{ t('nav.import_brickset') }}
    </a>
    {% endif %}
    <a href="/add" class="btn btn-primary">
      <i data-lucide="plus" style="width:15px;height:15px"></i>
      {{ t('add.title') }}
    </a>
  </div>
```

- [ ] **Step 2: Verify**

Run: `.venv/bin/pytest -v`
Expected: 79 passed.

Browser smoke: open `http://localhost:8128/` — verify the "Import from Brickset" link appears next to "Add Set" (only when Brickset quota is non-zero).

- [ ] **Step 3: Commit**

```
git add templates/index.html
git commit -m "feat(ui): add 'Import from Brickset' link to collection header

Visible only when Brickset quota > 0 so it disappears when the API
is unusable for the day."
```

---

## Phase 4 — Polish

### Task 11: Add i18n keys

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/de.json`

- [ ] **Step 1: Add to `locales/en.json`**

In the JSON top-level, add a new key `"import"` (preserve trailing commas correctly):

```json
  "import": {
    "title":                 "Import from Brickset",
    "intro":                 "This will pull every set you've marked as owned on Brickset and let you preview before importing.",
    "fetch_button":          "Fetch my Brickset collection",
    "fetching":              "Fetching...",
    "summary":               "Brickset reported {bs_total} owned sets. Will create {will_create} new rows across {sets_count} sets; will backfill brickset_set_id on {will_backfill} existing rows.",
    "col_bs_qty":            "Brickset",
    "col_local_qty":         "Local",
    "col_import":            "Import",
    "hint_partial":          "Local has fewer — adding the difference",
    "hint_already_covered":  "Already in collection — will backfill brickset_set_id if missing",
    "hint_local_richer":     "Local has more — sync any row to push {diff} back to Brickset",
    "submit_button":         "Import selected ({n} rows)",
    "flash_success":         "Imported {created} new rows; backfilled brickset_set_id on {backfilled} existing rows.",
    "error_quota":           "Brickset API daily quota exhausted. Try again tomorrow.",
    "error_fetch":           "Could not reach Brickset: {message}",
    "no_sets":               "Brickset returned no owned sets."
  },
```

Also add to `"nav"`:

```json
    "import_brickset": "Import from Brickset",
```

- [ ] **Step 2: Add to `locales/de.json`** (same keys, German values)

In the `"import"` block:

```json
  "import": {
    "title":                 "Aus Brickset importieren",
    "intro":                 "Hierbei werden alle Sets, die du auf Brickset als eigen markiert hast, abgerufen und zur Vorschau angezeigt.",
    "fetch_button":          "Meine Brickset-Sammlung abrufen",
    "fetching":              "Wird abgerufen…",
    "summary":               "Brickset meldet {bs_total} eigene Sets. {will_create} neue Einträge in {sets_count} Sets werden erstellt; brickset_set_id wird bei {will_backfill} bestehenden Einträgen ergänzt.",
    "col_bs_qty":            "Brickset",
    "col_local_qty":         "Lokal",
    "col_import":            "Importieren",
    "hint_partial":          "Lokal weniger — Differenz wird ergänzt",
    "hint_already_covered":  "Bereits in Sammlung — brickset_set_id wird ggf. ergänzt",
    "hint_local_richer":     "Lokal mehr — eine Zeile synchronisieren, um {diff} zurück an Brickset zu senden",
    "submit_button":         "Auswahl importieren ({n} Einträge)",
    "flash_success":         "{created} neue Einträge importiert; brickset_set_id bei {backfilled} bestehenden Einträgen ergänzt.",
    "error_quota":           "Brickset-API-Tageslimit erschöpft. Bitte morgen erneut versuchen.",
    "error_fetch":           "Brickset nicht erreichbar: {message}",
    "no_sets":               "Brickset meldet keine eigenen Sets."
  },
```

In `"nav"`:

```json
    "import_brickset": "Aus Brickset importieren",
```

- [ ] **Step 3: Validate JSON**

Run:
```
.venv/bin/python -c "import json; json.load(open('locales/en.json')); json.load(open('locales/de.json')); print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Verify**

Run: `.venv/bin/pytest -v`
Expected: 79 passed.

- [ ] **Step 5: Commit**

```
git add locales/en.json locales/de.json
git commit -m "feat(i18n): add Brickset import translation keys

15 new keys under 'import' plus one under 'nav' for the page-header
link. EN and DE in parity."
```

---

### Task 12: Add CSS for import preview rows

**Files:**
- Modify: `static/style.css` (append)
- Modify: `templates/base.html` (bump `?v=3` → `?v=4`)

- [ ] **Step 1: Bump the cache buster**

In `templates/base.html` line 8, change `style.css?v=3` to `style.css?v=4`.

- [ ] **Step 2: Append CSS to `static/style.css`**

At the end of `static/style.css`, append:

```css
/* ---------- Brickset Import ---------------------------------------- */
.import-summary {
  font: 400 13px/1.5 var(--font-body);
  color: var(--fg-muted);
  margin-bottom: var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  background: var(--bg-card);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
}

.import-preview-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}

.import-preview-row {
  background: var(--bg-card);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: var(--sp-3) var(--sp-4);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: var(--sp-2) var(--sp-4);
  align-items: center;
  transition: opacity var(--dur-fast) var(--ease-out);
}

.import-preview-row__pick {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  cursor: pointer;
  min-width: 0;
}
.import-preview-row__pick input[type="checkbox"] {
  margin-top: 6px;
  accent-color: var(--kuestenblau);
  cursor: pointer;
}
.import-preview-row__kicker {
  font: 500 10px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--sp-1);
}
.import-preview-row__name {
  font-family: var(--font-display);
  font-style: italic;
  font-weight: 400;
  font-size: 17px;
  line-height: 1.25;
  color: var(--fg-heading);
  margin-bottom: var(--sp-1);
}
.import-preview-row__meta {
  display: flex;
  gap: var(--sp-3);
  font: 400 12px/1 var(--font-mono);
  color: var(--fg-muted);
}
.import-preview-row__meta span { white-space: nowrap; }

.import-preview-row__qty {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--sp-1);
  font: 400 12px/1.4 var(--font-mono);
  color: var(--fg-muted);
}
.import-preview-row__qty strong {
  color: var(--fg);
  font-weight: 600;
}
.import-preview-row__qty label {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
}
.import-preview-row__qty input[type="number"] {
  width: 70px;
  font: 400 14px/1 var(--font-mono);
  padding: 4px 8px;
  border: 1px solid rgba(27,58,92,.28);
  border-radius: var(--r-md);
  background: var(--weiss);
  text-align: right;
}

.import-preview-row__hint {
  grid-column: 1 / -1;
  font: 400 11px/1.4 var(--font-body);
  font-style: italic;
  color: var(--fg-muted);
  padding-left: var(--sp-5);
}

.flash-banner {
  margin-bottom: var(--sp-4);
}
```

- [ ] **Step 3: Verify**

Run: `.venv/bin/pytest -v`
Expected: 79 passed.

Browser smoke: open `http://localhost:8128/import/brickset` → click Fetch. Confirm rows are styled correctly (card layout, accent for active checkbox, right-aligned qty input).

- [ ] **Step 4: Commit**

```
git add static/style.css templates/base.html
git commit -m "style: add Brickset import preview row styles + bump cache buster

Card layout per row with the pick controls on the left and the
qty + counts on the right. Matches the existing palette."
```

---

### Task 13: Final end-to-end manual verification

**Files:** none modified.

Walk through the full import flow in the browser in both DE and EN.

- [ ] **Step 1: Fresh server**

Stop any existing uvicorn on :8123, then start: `.venv/bin/uvicorn main:app --port 8123 --reload`. Wait for "Server ready".

- [ ] **Step 2: Header link**

Visit `http://localhost:8123/` — verify "Import from Brickset" link appears between (or near) the "Add Set" button and is the right language.

- [ ] **Step 3: Page render**

Click the link → land on `/import/brickset`. The intro paragraph and "Fetch" button visible.

- [ ] **Step 4: Fetch**

Click "Fetch my Brickset collection". The button shows "Fetching..." briefly. Within a few seconds, the preview table appears with one row per owned set Brickset reports.

For each row, verify:
- Set number, name, theme, year visible
- "Brickset: N | Local: M | Import: [X]" matches reality
- Hint text appears for any row where local_qty > 0

- [ ] **Step 5: Adjust counts**

- Untick one row → row visually dims and the submit-button label decrements
- Raise a count → submit label increments
- Set a row's count to 0 but leave ticked → row stays ticked but contributes 0 to the count

- [ ] **Step 6: Commit**

Click "Import selected (N rows)". Browser redirects to `/?imported=...&backfilled=...`. The green flash banner appears at the top. Collection list shows the new rows.

- [ ] **Step 7: Idempotency**

Click "Import from Brickset" again → fetch again. The same sets now show "Local: matches Brickset" with default import = 0. Submit doesn't create dupes.

- [ ] **Step 8: Language toggle**

Switch DE ↔ EN at any point. Labels translate correctly.

- [ ] **Step 9: Quota awareness**

If you've exhausted Brickset's daily quota (unlikely), the header link should disappear and the fetch endpoint should show the quota-exceeded callout.

- [ ] **Step 10: Mark verification commit**

```
git commit --allow-empty -m "chore: verify Brickset bulk import end-to-end

All steps in plan Task 13 pass in both DE and EN."
```

---

## Done

Iteration 3.5 complete. The user can now pull their Brickset-owned LEGO collection into the local DB with:

- Per-set preview showing Brickset qty vs local qty
- Editable per-row import count (default = difference, user can adjust)
- Optional per-row exclusion via checkbox
- Auto-backfill of `brickset_set_id` on existing rows that lacked it
- Multi-copy support (e.g. 3 Magical Unicorn builds become 3 local rows)
- Status flash on the collection list

Next on the V1 path: **Iteration 4 (details view) → code review → Phase T (LaunchAgent)**.
