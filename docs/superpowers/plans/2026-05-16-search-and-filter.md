# Search + Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a search box and a collapsible faceted filter panel to the `/` collection page, with server-side filtering, URL-encoded state, dynamic facet counts, and a live-updating HTML partial.

**Architecture:** Server renders the page fully on first load (back-button-friendly URL state). After that, search input and filter checkboxes fetch an HTML partial from `GET /api/sets/filter` and the JS swaps the results region. Faceted filter counts are computed with the standard "ignore own facet's filter" semantics. Search is case-insensitive across all text fields, using a Python-registered SQLite function for proper Unicode handling.

**Tech Stack:** FastAPI 0.115, Starlette 1.0, Jinja2 3.1, SQLite (via stdlib `sqlite3`), pytest (newly added), vanilla JS (no framework).

**Spec:** `docs/superpowers/specs/2026-05-16-search-and-filter-design.md`

---

## Phase 0 — Foundation

### Task 1: Initialize git repository

**Files:**
- Create: `.gitignore` (extend)
- Verify: existing `.gitignore` already excludes `__pycache__`, `.venv`, `.tmp`, `data`, `uploads`, `.env`

- [ ] **Step 1: Inspect current `.gitignore`**

Run: `cat .gitignore`
Expected: existing entries for ignored paths. If `data/`, `uploads/`, `.env`, `.venv/`, `__pycache__/`, `.tmp/`, and `.DS_Store` are not all present, add the missing ones.

- [ ] **Step 2: Ensure `.gitignore` is complete**

Final contents should include at minimum:

```
__pycache__/
*.pyc
.venv/
.env
.tmp/
.DS_Store
data/*.db
data/*.db-journal
uploads/
docs/superpowers/specs/*.draft.md
```

If any lines are missing, append them.

- [ ] **Step 3: Initialize git**

Run: `git init`
Expected: `Initialized empty Git repository in /Users/hhalfpap/git/projects/own/brickset-tracker/.git/`

- [ ] **Step 4: Initial commit of current state**

Run:
```
git add .gitignore CLAUDE.md main.py requirements.txt architecture execution navigation locales static templates docs
git status
```
Verify no `.env`, `data/`, `uploads/`, or `__pycache__/` shows in staged files.

Then:
```
git commit -m "chore: initial commit — Iterations 1+2 complete

State at the start of Iteration 3 (search + filter).
Add, edit, delete, EAN lookup, photos, i18n all working."
```

Expected: commit succeeds. Run `git log --oneline` to confirm one commit exists.

---

### Task 2: Add pytest and create test scaffold

**Files:**
- Modify: `requirements.txt` (add pytest, pytest-asyncio)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`
- Create: `pytest.ini`

- [ ] **Step 1: Add test dependencies to `requirements.txt`**

Append to `requirements.txt`:
```
pytest==8.3.4
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Install them**

Run: `.venv/bin/pip install -r requirements.txt`
Expected: pytest and pytest-asyncio installed. Confirm with `.venv/bin/pytest --version` → `pytest 8.3.4`.

- [ ] **Step 3: Create `pytest.ini`**

Write `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
asyncio_mode = auto
filterwarnings =
    ignore::DeprecationWarning
```

- [ ] **Step 4: Create `tests/__init__.py`**

Write `tests/__init__.py` as an empty file (one blank line is fine).

- [ ] **Step 5: Write smoke test**

Write `tests/test_smoke.py`:
```python
"""Sanity check: pytest discovers and runs."""


def test_pytest_runs():
    assert 1 + 1 == 2
```

- [ ] **Step 6: Run smoke test**

Run: `.venv/bin/pytest -v`
Expected: `tests/test_smoke.py::test_pytest_runs PASSED` and 1 test in summary.

- [ ] **Step 7: Commit**

```
git add requirements.txt pytest.ini tests/
git commit -m "chore: add pytest with smoke test

Foundation for Iteration 3 TDD work. Future iterations will
backfill tests for Iterations 1 and 2."
```

---

### Task 3: Test DB fixture and sample data factory

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/factories.py`
- Create: `tests/test_db_fixture.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_db_fixture.py`:
```python
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
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/pytest tests/test_db_fixture.py -v`
Expected: FAIL with "fixture 'db' not found".

- [ ] **Step 3: Implement the `db` fixture**

Write `tests/conftest.py`:
```python
"""Shared pytest fixtures."""
import sqlite3
from pathlib import Path

import pytest

from execution import db as db_module
from execution.db import init_db


@pytest.fixture
def db(tmp_path: Path, monkeypatch) -> Path:
    """Per-test SQLite database in a temp file.

    Monkeypatches execution.db.DB_PATH so any code calling
    get_connection() during the test uses the temp DB. The temp
    file is cleaned up automatically when the test exits.
    """
    test_db_path = tmp_path / "test_brickset.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db_path)
    init_db()
    yield test_db_path
```

- [ ] **Step 4: Run tests, confirm they pass**

Run: `.venv/bin/pytest tests/test_db_fixture.py -v`
Expected: 3 passed.

- [ ] **Step 5: Create the set factory**

Write `tests/factories.py`:
```python
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
    ean: str | None = None,
    status: str = "complete",
) -> int:
    """Insert a set row and return its id."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO sets
               (brand, set_number, name, part_count, condition, location,
                date_of_purchase, note, theme, release_year, minifigs,
                price_paid, ean, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (brand, set_number, name, part_count, condition, location,
             date_of_purchase, note, theme, release_year, minifigs,
             price_paid, ean, status),
        )
        return cur.lastrowid
```

- [ ] **Step 6: Verify factory works**

Append to `tests/test_db_fixture.py`:
```python
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
```

Run: `.venv/bin/pytest tests/test_db_fixture.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```
git add tests/conftest.py tests/factories.py tests/test_db_fixture.py
git commit -m "test: add isolated DB fixture and set factory

Each test gets a fresh in-tempdir SQLite DB. Factory helper
keeps test setup DRY."
```

---

## Phase 1 — Backend (TDD)

### Task 4: Register `py_lower` SQLite function

**Files:**
- Modify: `execution/db.py`
- Create: `tests/test_db_py_lower.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_db_py_lower.py`:
```python
"""py_lower is a Python-backed SQLite function that handles Unicode
case-folding properly (SQLite's built-in LOWER is ASCII-only)."""
from execution.db import get_connection


def test_py_lower_ascii(db):
    with get_connection() as conn:
        result = conn.execute("SELECT py_lower('HELLO')").fetchone()[0]
    assert result == "hello"


def test_py_lower_umlauts(db):
    with get_connection() as conn:
        result = conn.execute("SELECT py_lower('MÖBEL')").fetchone()[0]
    assert result == "möbel"


def test_py_lower_handles_null(db):
    with get_connection() as conn:
        result = conn.execute("SELECT py_lower(NULL)").fetchone()[0]
    assert result is None
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_db_py_lower.py -v`
Expected: FAIL with `no such function: py_lower`.

- [ ] **Step 3: Register the function in `execution/db.py`**

Modify `execution/db.py` — change the `get_connection` function to register `py_lower`:

```python
def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.create_function(
        "py_lower", 1, lambda s: s.lower() if s is not None else None
    )
    return conn
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_db_py_lower.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add execution/db.py tests/test_db_py_lower.py
git commit -m "feat(db): register py_lower for Unicode case-insensitive matching

SQLite's built-in LOWER() is ASCII-only. py_lower delegates to
Python's str.lower() which folds umlauts correctly. Used by the
upcoming search feature."
```

---

### Task 5: Extend `get_sets()` with search query parameter

**Files:**
- Modify: `navigation/set_manager.py` (existing `get_sets` function around line 78)
- Create: `tests/test_get_sets_search.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_get_sets_search.py`:
```python
"""get_sets(q=...) does a case-insensitive substring match across all
text-ish fields: name, brand, set_number, ean, theme, note, location,
condition, release_year, part_count."""
from navigation.set_manager import get_sets
from tests.factories import make_set


def test_search_matches_name(db):
    make_set(name="Star Wars X-Wing", set_number="11111")
    make_set(name="City Police Station", set_number="22222")
    results = get_sets(q="x-wing")
    assert len(results) == 1
    assert results[0]["set_number"] == "11111"


def test_search_is_case_insensitive(db):
    make_set(name="Tower Bridge", set_number="10214")
    results = get_sets(q="TOWER")
    assert len(results) == 1


def test_search_matches_umlauts(db):
    make_set(name="Schöne Möbel", set_number="99999")
    results = get_sets(q="möbel")
    assert len(results) == 1


def test_search_matches_brand(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(q="bluebrixx")
    assert len(results) == 1
    assert results[0]["set_number"] == "2"


def test_search_matches_set_number(db):
    make_set(set_number="42171", name="A")
    make_set(set_number="10214", name="B")
    results = get_sets(q="42171")
    assert len(results) == 1


def test_search_matches_ean(db):
    make_set(ean="5702017595672", name="A", set_number="1")
    make_set(ean="4060904018514", name="B", set_number="2")
    results = get_sets(q="5702017")
    assert len(results) == 1


def test_search_matches_theme(db):
    make_set(theme="Star Wars", name="A", set_number="1")
    make_set(theme="City", name="B", set_number="2")
    results = get_sets(q="star wars")
    assert len(results) == 1


def test_search_matches_note(db):
    make_set(note="Birthday gift from Tim", name="A", set_number="1")
    make_set(note="", name="B", set_number="2")
    results = get_sets(q="tim")
    assert len(results) == 1


def test_search_matches_location(db):
    make_set(location="Living room shelf", name="A", set_number="1")
    make_set(location="Basement", name="B", set_number="2")
    results = get_sets(q="shelf")
    assert len(results) == 1


def test_search_matches_release_year(db):
    make_set(release_year=2024, name="A", set_number="1")
    make_set(release_year=1999, name="B", set_number="2")
    results = get_sets(q="2024")
    assert len(results) == 1


def test_search_matches_part_count(db):
    make_set(part_count=3893, name="A", set_number="1")
    make_set(part_count=42, name="B", set_number="2")
    results = get_sets(q="3893")
    assert len(results) == 1


def test_search_empty_string_returns_all(db):
    make_set(name="A", set_number="1")
    make_set(name="B", set_number="2")
    assert len(get_sets(q="")) == 2
    assert len(get_sets(q=None)) == 2


def test_search_no_match_returns_empty(db):
    make_set(name="A", set_number="1")
    results = get_sets(q="nonexistent")
    assert results == []
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_get_sets_search.py -v`
Expected: all tests fail with `TypeError: get_sets() got an unexpected keyword argument 'q'`.

- [ ] **Step 3: Extend `get_sets()` to accept `q`**

Replace the existing `get_sets` function in `navigation/set_manager.py` with:

```python
def get_sets(
    sort_by: str = "date_of_purchase",
    sort_dir: str = "DESC",
    q: str | None = None,
) -> list[dict]:
    """Return all set records matching the given filters."""
    if sort_by not in SORT_ALLOWLIST:
        sort_by = "date_of_purchase"
    sort_dir = "ASC" if sort_dir.upper() == "ASC" else "DESC"

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

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT id, ean, brand, set_number, name, part_count, condition,
                       location, date_of_purchase, note, theme, release_year,
                       web_images, own_photos, minifigs, price_paid,
                       brickset_set_id, status, created_at
                FROM sets
                {where_sql}
                ORDER BY {sort_by} {sort_dir}, id DESC""",
            params,
        ).fetchall()

    return [_row_to_dict(r) for r in rows]
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_get_sets_search.py -v`
Expected: 13 passed.

Also run the full suite to confirm no regression:
Run: `.venv/bin/pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add navigation/set_manager.py tests/test_get_sets_search.py
git commit -m "feat(sets): add q= search parameter to get_sets

Substring match across name, brand, set_number, ean, theme,
note, location, condition, release_year, part_count.
Case-insensitive and Unicode-aware (via py_lower)."
```

---

### Task 6: Extend `get_sets()` with multi-facet filters

**Files:**
- Modify: `navigation/set_manager.py` (the same `get_sets` function)
- Create: `tests/test_get_sets_filters.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_get_sets_filters.py`:
```python
"""get_sets() supports brand/condition/theme/status list filters.
Within a facet: OR. Across facets: AND."""
from navigation.set_manager import get_sets
from tests.factories import make_set


def test_brand_filter_single(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(brands=["LEGO"])
    assert len(results) == 1
    assert results[0]["brand"] == "LEGO"


def test_brand_filter_multiple_is_or(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    make_set(brand="Cobi", name="C", set_number="3")
    results = get_sets(brands=["LEGO", "Cobi"])
    assert {r["brand"] for r in results} == {"LEGO", "Cobi"}


def test_condition_filter(db):
    make_set(condition="ovp", name="A", set_number="1")
    make_set(condition="gebaut", name="B", set_number="2")
    results = get_sets(conditions=["gebaut"])
    assert len(results) == 1
    assert results[0]["condition"] == "gebaut"


def test_theme_filter(db):
    make_set(theme="Star Wars", name="A", set_number="1")
    make_set(theme="City", name="B", set_number="2")
    results = get_sets(themes=["Star Wars"])
    assert len(results) == 1


def test_status_filter(db):
    make_set(status="complete", name="A", set_number="1")
    make_set(status="draft", name="B", set_number="2")
    results = get_sets(statuses=["draft"])
    assert len(results) == 1
    assert results[0]["status"] == "draft"


def test_facets_combine_as_and(db):
    # Only one row matches both brand=LEGO AND condition=gebaut
    make_set(brand="LEGO", condition="gebaut", name="A", set_number="1")
    make_set(brand="LEGO", condition="ovp", name="B", set_number="2")
    make_set(brand="BlueBrixx", condition="gebaut", name="C", set_number="3")
    results = get_sets(brands=["LEGO"], conditions=["gebaut"])
    assert len(results) == 1
    assert results[0]["name"] == "A"


def test_search_and_filters_combine(db):
    make_set(brand="LEGO", name="Star Wars X-Wing", set_number="1")
    make_set(brand="LEGO", name="City Police", set_number="2")
    make_set(brand="BlueBrixx", name="Star Wars Replica", set_number="3")
    results = get_sets(q="star wars", brands=["LEGO"])
    assert len(results) == 1
    assert results[0]["set_number"] == "1"


def test_empty_filter_list_means_no_filter(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(brands=[])
    assert len(results) == 2


def test_none_filter_means_no_filter(db):
    make_set(brand="LEGO", name="A", set_number="1")
    make_set(brand="BlueBrixx", name="B", set_number="2")
    results = get_sets(brands=None)
    assert len(results) == 2
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_get_sets_filters.py -v`
Expected: TypeError on unexpected kwargs.

- [ ] **Step 3: Extend `get_sets()` with facet filter args**

Replace the `get_sets` function with this version:

```python
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
                       web_images, own_photos, minifigs, price_paid,
                       brickset_set_id, status, created_at
                FROM sets
                {where_sql}
                ORDER BY {sort_by} {sort_dir}, id DESC""",
            params,
        ).fetchall()

    return [_row_to_dict(r) for r in rows]


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
```

The `_build_filter_clauses` helper is also reused by `get_facet_counts` in Task 8, so factoring it out now keeps the code DRY.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_get_sets_filters.py -v`
Expected: 9 passed.

Then run the search tests again to verify the refactor didn't break them:
Run: `.venv/bin/pytest tests/test_get_sets_search.py tests/test_get_sets_filters.py -v`
Expected: 22 passed total.

- [ ] **Step 5: Commit**

```
git add navigation/set_manager.py tests/test_get_sets_filters.py
git commit -m "feat(sets): add brand/condition/theme/status filters to get_sets

OR within a facet (IN clause), AND across facets. Empty list and
None both mean 'no filter on this dimension'. Filter clause builder
factored out for reuse by facet count queries."
```

---

### Task 7: Add `count_all_sets()` helper

**Files:**
- Modify: `navigation/set_manager.py`
- Create: `tests/test_count_all_sets.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_count_all_sets.py`:
```python
from navigation.set_manager import count_all_sets
from tests.factories import make_set


def test_count_all_sets_empty(db):
    assert count_all_sets() == 0


def test_count_all_sets_with_rows(db):
    make_set(name="A", set_number="1")
    make_set(name="B", set_number="2")
    make_set(name="C", set_number="3")
    assert count_all_sets() == 3


def test_count_all_sets_includes_drafts(db):
    make_set(name="A", set_number="1", status="complete")
    make_set(name="B", set_number="2", status="draft")
    assert count_all_sets() == 2
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_count_all_sets.py -v`
Expected: ImportError or AttributeError on `count_all_sets`.

- [ ] **Step 3: Add the helper to `navigation/set_manager.py`**

Append to `navigation/set_manager.py` (place it next to `get_sets`):

```python
def count_all_sets() -> int:
    """Total set count across the whole collection, ignoring all filters."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sets").fetchone()
    return row["n"]
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_count_all_sets.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add navigation/set_manager.py tests/test_count_all_sets.py
git commit -m "feat(sets): add count_all_sets for the 'X of Y' display"
```

---

### Task 8: Add `get_facet_counts()` with own-filter-excluded semantics

**Files:**
- Modify: `navigation/set_manager.py`
- Create: `tests/test_get_facet_counts.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_get_facet_counts.py`:
```python
"""get_facet_counts returns the distinct values + counts for each
facet (brand, condition, theme, status), respecting the current search
and all OTHER facet filters but NOT the facet's own filter.

This is what lets a user click "LEGO" in the brand facet and still
see "BlueBrixx (3)" so they can switch."""
from navigation.set_manager import get_facet_counts
from tests.factories import make_set


def test_facet_counts_unfiltered(db):
    make_set(brand="LEGO", condition="ovp", theme="Star Wars", set_number="1")
    make_set(brand="LEGO", condition="gebaut", theme="City", set_number="2")
    make_set(brand="BlueBrixx", condition="ovp", theme="Castle", set_number="3")

    facets = get_facet_counts()

    assert facets["brand"] == {"LEGO": 2, "BlueBrixx": 1}
    assert facets["condition"] == {"ovp": 2, "gebaut": 1}
    assert facets["theme"] == {"Star Wars": 1, "City": 1, "Castle": 1}
    assert facets["status"] == {"complete": 3}


def test_facet_counts_respects_search(db):
    make_set(brand="LEGO", name="Star Wars X-Wing", set_number="1")
    make_set(brand="LEGO", name="City Police", set_number="2")
    make_set(brand="BlueBrixx", name="Star Wars Replica", set_number="3")

    facets = get_facet_counts(q="star wars")
    assert facets["brand"] == {"LEGO": 1, "BlueBrixx": 1}


def test_brand_facet_ignores_brand_filter(db):
    """When the user has ticked 'LEGO' in the brand facet, the brand facet
    itself must still show BlueBrixx so they can switch. Other facets
    DO honour the brand filter."""
    make_set(brand="LEGO", condition="ovp", set_number="1")
    make_set(brand="LEGO", condition="gebaut", set_number="2")
    make_set(brand="BlueBrixx", condition="ovp", set_number="3")
    make_set(brand="BlueBrixx", condition="ovp", set_number="4")

    facets = get_facet_counts(brands=["LEGO"])

    # brand facet ignores its own filter — shows everyone
    assert facets["brand"] == {"LEGO": 2, "BlueBrixx": 2}
    # condition facet respects the brand filter — only LEGO conditions
    assert facets["condition"] == {"ovp": 1, "gebaut": 1}


def test_condition_facet_ignores_condition_filter(db):
    make_set(brand="LEGO", condition="ovp", set_number="1")
    make_set(brand="LEGO", condition="gebaut", set_number="2")
    make_set(brand="BlueBrixx", condition="ovp", set_number="3")

    facets = get_facet_counts(conditions=["ovp"])

    # condition facet ignores its own filter
    assert facets["condition"] == {"ovp": 2, "gebaut": 1}
    # brand facet respects the condition filter — only ovp brands
    assert facets["brand"] == {"LEGO": 1, "BlueBrixx": 1}


def test_facet_excludes_null_values(db):
    make_set(brand="LEGO", theme=None, set_number="1")
    make_set(brand="LEGO", theme="City", set_number="2")
    make_set(brand="BlueBrixx", theme=None, set_number="3")

    facets = get_facet_counts()

    # NULL theme is not surfaced as a facet option
    assert facets["theme"] == {"City": 1}
    # brand still counts every row
    assert facets["brand"] == {"LEGO": 2, "BlueBrixx": 1}


def test_facet_returns_empty_dict_when_no_rows(db):
    facets = get_facet_counts()
    assert facets == {"brand": {}, "condition": {}, "theme": {}, "status": {}}
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_get_facet_counts.py -v`
Expected: ImportError / AttributeError on `get_facet_counts`.

- [ ] **Step 3: Implement `get_facet_counts`**

Append to `navigation/set_manager.py`:

```python
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
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_get_facet_counts.py -v`
Expected: 6 passed.

Run the full backend suite to confirm no regressions:
Run: `.venv/bin/pytest -v`
Expected: all backend tests pass (smoke + db fixture + py_lower + search + filters + count + facets).

- [ ] **Step 5: Commit**

```
git add navigation/set_manager.py tests/test_get_facet_counts.py
git commit -m "feat(sets): add get_facet_counts with own-filter-excluded semantics

For each facet (brand/condition/theme/status), counts honour all
other facet filters and the search query but not the facet's own
filter. This lets users switch values within a facet without
unticking first. NULL values are not surfaced as facet options."
```

---

## Phase 2 — Routes (TDD)

### Task 9: Extend `/` route with filter query params

**Files:**
- Modify: `main.py` (existing `index` function around line 53)
- Create: `tests/test_index_route.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_index_route.py`:
```python
"""GET / accepts search and filter query params and feeds them through
to get_sets / get_facet_counts. Smoke-level — verifies the route wires
the params through, not the underlying SQL behaviour (that's covered
in Phase 1)."""
from fastapi.testclient import TestClient

from main import app
from tests.factories import make_set


def test_index_renders_empty_collection(db):
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "No sets yet" in r.text or "Noch keine Sets" in r.text


def test_index_renders_all_sets_by_default(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="LEGO", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Apple" in r.text
    assert "Banana" in r.text


def test_index_q_param_narrows_results(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="LEGO", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/?q=apple")
    assert "Apple" in r.text
    assert "Banana" not in r.text


def test_index_brand_param_filters(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="BlueBrixx", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/?brand=LEGO")
    assert "Apple" in r.text
    assert "Banana" not in r.text


def test_index_brand_param_is_repeatable(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="BlueBrixx", name="Banana", set_number="2")
    make_set(brand="Cobi", name="Cherry", set_number="3")
    client = TestClient(app)
    r = client.get("/?brand=LEGO&brand=BlueBrixx")
    assert "Apple" in r.text
    assert "Banana" in r.text
    assert "Cherry" not in r.text


def test_index_combines_search_and_filter(db):
    make_set(brand="LEGO", name="Star Wars X-Wing", set_number="1")
    make_set(brand="LEGO", name="City Police", set_number="2")
    make_set(brand="BlueBrixx", name="Star Wars Replica", set_number="3")
    client = TestClient(app)
    r = client.get("/?q=star+wars&brand=LEGO")
    assert "X-Wing" in r.text
    assert "City Police" not in r.text
    assert "Replica" not in r.text
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_index_route.py -v`
Expected: failures — the route doesn't yet accept these params, so it'll either return all rows or 422.

- [ ] **Step 3: Update the route**

In `main.py`, replace the `index` function with:

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
):
    # Sanitise search
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
    ))
```

And update the imports at the top of `main.py` — add `Query` and `count_all_sets`/`get_facet_counts`:

```python
from fastapi import FastAPI, Form, Query, Request, UploadFile, File
```

```python
from navigation.set_manager import (
    CONDITION_VALUES, count_all_sets, count_owned, delete_set, get_brands,
    get_facet_counts, get_set, get_sets, save_set, update_set
)
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_index_route.py -v`
Expected: 6 passed. (Some tests rely on names appearing in the rendered HTML; if a test fails because the template doesn't render those names in this format yet, that's still fine for this task — but the route itself should not error.)

If a test fails purely because of template content (e.g., the empty-state message is in a different language than asserted), accept the failure for now and re-run after Phase 3 templates are in place. Mark the failing test name in a comment with `# re-verify after Phase 3`.

Actually — better approach: make the test independent of locale by checking for the rendered set names only, which always appear verbatim:

```python
def test_index_renders_empty_collection(db):
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    # An empty collection has no <div class="set-card"> elements
    assert 'class="set-card"' not in r.text
```

Apply that change if `test_index_renders_empty_collection` fails on locale strings.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```
git add main.py tests/test_index_route.py
git commit -m "feat(routes): wire search and filter query params into GET /

Repeated singular query params (?brand=X&brand=Y) collected into
lists for the get_sets/get_facet_counts plural args.
Search query trimmed and capped at 200 chars; unknown facet
values pass through and silently match nothing."
```

---

### Task 10: Add `GET /api/sets/filter` route returning HTML partial

**Files:**
- Modify: `main.py`
- Create: `templates/_results_partial.html` (stub for now; fully built in Task 11)
- Create: `tests/test_api_filter_route.py`

- [ ] **Step 1: Write a placeholder partial template**

Write `templates/_results_partial.html` as a stub — Task 11 will replace its contents:

```html
{# Placeholder. Replaced by Task 11. #}
<div id="results-region" data-total="{{ total }}" data-shown="{{ sets|length }}">
{% if sets %}
  <ul class="set-list">
    {% for s in sets %}
    <li class="set-card" data-set-id="{{ s.id }}">{{ s.brand }} {{ s.set_number }} — {{ s.name }}</li>
    {% endfor %}
  </ul>
{% else %}
  <div class="empty-state">No sets match</div>
{% endif %}
</div>
```

This stub is enough for the route test to assert structure.

- [ ] **Step 2: Write the failing tests**

Write `tests/test_api_filter_route.py`:
```python
"""GET /api/sets/filter returns an HTML partial (no full page chrome)."""
from fastapi.testclient import TestClient

from main import app
from tests.factories import make_set


def test_partial_returns_200_html(db):
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_partial_has_no_html_chrome(db):
    """The partial should NOT include <html>, <head>, or <body> tags."""
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    body = r.text.lower()
    assert "<html" not in body
    assert "<head" not in body
    assert "<body" not in body


def test_partial_contains_results_region(db):
    make_set(name="Apple", set_number="1")
    client = TestClient(app)
    r = client.get("/api/sets/filter")
    assert 'id="results-region"' in r.text
    assert "Apple" in r.text


def test_partial_honours_search(db):
    make_set(name="Apple", set_number="1")
    make_set(name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/api/sets/filter?q=apple")
    assert "Apple" in r.text
    assert "Banana" not in r.text


def test_partial_honours_brand_filter(db):
    make_set(brand="LEGO", name="Apple", set_number="1")
    make_set(brand="BlueBrixx", name="Banana", set_number="2")
    client = TestClient(app)
    r = client.get("/api/sets/filter?brand=LEGO")
    assert "Apple" in r.text
    assert "Banana" not in r.text
```

- [ ] **Step 3: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_api_filter_route.py -v`
Expected: 404 (route doesn't exist) on all tests.

- [ ] **Step 4: Add the route to `main.py`**

After the `index` function in `main.py`, append:

```python
@app.get("/api/sets/filter", response_class=HTMLResponse)
async def api_filter(
    request: Request,
    sort: str = "date_of_purchase",
    dir: str = "DESC",
    q: str | None = None,
    brand: list[str] = Query(default_factory=list),
    condition: list[str] = Query(default_factory=list),
    theme: list[str] = Query(default_factory=list),
    status: list[str] = Query(default_factory=list),
):
    """Returns just the results region as an HTML partial — for live filtering."""
    q_clean = (q or "").strip()[:200] or None

    sets = get_sets(
        sort_by=sort, sort_dir=dir, q=q_clean,
        brands=brand, conditions=condition,
        themes=theme, statuses=status,
    )
    total = count_all_sets()

    return templates.TemplateResponse(request, "_results_partial.html", context=_ctx(
        request, sets=sets, total=total,
        active_filters={"brand": brand, "condition": condition,
                        "theme": theme, "status": status},
        q=q_clean or "",
    ))
```

- [ ] **Step 5: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_api_filter_route.py -v`
Expected: 5 passed.

Run full suite:
Run: `.venv/bin/pytest -v`
Expected: all green.

- [ ] **Step 6: Commit**

```
git add main.py templates/_results_partial.html tests/test_api_filter_route.py
git commit -m "feat(api): add GET /api/sets/filter returning HTML partial

Stub _results_partial.html for now; Task 11 replaces it with the
real results region content."
```

---

## Phase 3 — Templates (manual verification)

> Tests for these tasks would mostly assert template contents which is brittle. We rely on browser verification at the end of each task, plus the route smoke tests already written.

### Task 11: Build the real `_results_partial.html`

**Files:**
- Modify: `templates/_results_partial.html` (replace stub from Task 10)
- Modify: `templates/index.html` (we'll add the include and remove the moved block in Task 12, but the partial must work standalone first)

- [ ] **Step 1: Replace the stub partial with the full results region**

Overwrite `templates/_results_partial.html`:

```html
{# Results region — included by index.html and returned by /api/sets/filter #}
{% set total_active_filters =
    (active_filters.brand | length) +
    (active_filters.condition | length) +
    (active_filters.theme | length) +
    (active_filters.status | length) %}
{% set filters_active = (q | length > 0) or (total_active_filters > 0) %}

<div id="results-region" data-total="{{ total }}" data-shown="{{ sets | length }}">

  {% if filters_active and sets %}
  <p class="results-count">
    <i data-lucide="filter" style="width:13px;height:13px;vertical-align:-2px"></i>
    {{ t('list.results_count', shown=sets|length, total=total) }}
  </p>
  {% endif %}

  {% if sets %}

  {# Condition colour map (duplicated from index.html for partial independence) #}
  {% set cond_class = {
    'ovp':      'cond-ovp',
    'im_bau':   'cond-im_bau',
    'gebaut':   'cond-gebaut',
    'abgebaut': 'cond-abgebaut',
    'verkauft': 'cond-verkauft',
  } %}

  <div class="set-list">
    {% for s in sets %}
    {% set thumb = '' %}
    {% if s.own_photos %}{% set thumb = '/' ~ s.own_photos[0] %}
    {% elif s.web_images %}{% set thumb = '/api/proxy-image?url=' ~ (s.web_images[0] | urlencode) %}
    {% endif %}
    <div class="set-card">

      <div class="set-card__thumb">
        {% if thumb %}
          <img src="{{ thumb }}" alt="" loading="lazy">
        {% else %}
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="20" cy="21" r="6"/><circle cx="36" cy="21" r="6"/>
            <rect x="10" y="27" width="36" height="16" rx="3"/>
          </svg>
        {% endif %}
      </div>

      <div class="set-card__left">
        <div class="set-card__kicker">
          {{ s.brand | upper }} · <span class="mono">{{ s.set_number }}</span>
        </div>
        <div class="set-card__name" title="{{ s.name }}">{{ s.name }}</div>
        <div class="set-card__meta">
          {% if s.part_count %}
            <span>{{ "{:,}".format(s.part_count).replace(",", ".") }} {{ t('list.sort_parts') | lower }}</span>
          {% endif %}
          {% if s.price_paid %}
            <span>{{ "%.2f"|format(s.price_paid) }} €</span>
          {% endif %}
          {% if s.date_of_purchase %}
            <span class="mono">{{ s.date_of_purchase }}</span>
          {% endif %}
          {% if s.theme %}
            <span>{{ s.theme }}</span>
          {% endif %}
        </div>
      </div>

      <div class="set-card__right">
        {% if s.status == 'draft' %}
          <span class="draft-badge">{{ t('list.draft_badge') }}</span>
        {% endif %}
        {% if s.condition %}
          <span class="condition-tag {{ cond_class.get(s.condition, '') }}">
            {{ t('condition.' ~ s.condition) }}
          </span>
        {% endif %}
        <div class="set-card__actions">
          {% if s.brickset_set_id and s.brand | lower == 'lego' %}
          <button class="btn btn-secondary btn-sm" title="{{ t('add.sync_brickset') }}"
                  onclick="syncBrickset({{ s.id }}, this)">
            <i data-lucide="refresh-cw" style="width:13px;height:13px"></i>
          </button>
          {% endif %}
          <a href="/sets/{{ s.id }}/edit" class="btn btn-ghost btn-sm" title="{{ t('edit.title') }}">
            <i data-lucide="pencil" style="width:13px;height:13px"></i>
          </a>
          <button class="btn btn-ghost btn-sm"
                  onclick="openDeleteModal({{ s.id }}, '{{ s.name | replace("'", "\\'") }}')">
            <i data-lucide="trash-2" style="width:13px;height:13px"></i>
          </button>
        </div>
      </div>

    </div>
    {% endfor %}
  </div>

  {% elif filters_active %}

  {# Filtered to zero — distinct from "collection is empty" #}
  <div class="empty-state">
    <h2>{{ t('list.no_matches') }}</h2>
    <a href="/" class="btn btn-ghost" style="margin-top:16px">
      <i data-lucide="x" style="width:15px;height:15px"></i>
      {{ t('list.filter_clear_all') }}
    </a>
  </div>

  {% else %}

  {# Genuinely empty collection #}
  <div class="empty-state">
    <h2>{{ t('list.empty') }}</h2>
    <a href="/add" class="btn btn-primary" style="margin-top:16px">
      <i data-lucide="plus"></i> {{ t('nav.add_set') }}
    </a>
  </div>

  {% endif %}

</div>
```

- [ ] **Step 2: Re-run the route tests**

Run: `.venv/bin/pytest tests/test_api_filter_route.py tests/test_index_route.py -v`
Expected: all green. The partial is now substantive enough that "Apple" / "Banana" assertions find content inside the cards.

- [ ] **Step 3: Smoke-test in the browser**

Start the server (if not running):
Run: `.venv/bin/uvicorn main:app --port 8123` (run in background or another shell)

Open `http://localhost:8123/`. Expected: collection list looks identical to before. No visual change yet (we haven't added search/filter UI to `index.html`).

- [ ] **Step 4: Commit**

```
git add templates/_results_partial.html
git commit -m "feat(templates): build full _results_partial.html

Includes result-count line, set cards, filtered-empty and
genuinely-empty states. Used by both / and /api/sets/filter."
```

---

### Task 12: Wire the partial into `index.html` + add the search bar

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Read the current `index.html`**

Open `templates/index.html` and confirm the existing structure: page header, sort bar, condition class map, set list loop, empty state, scripts.

- [ ] **Step 2: Replace the body of the `{% block content %}` with this new structure**

Replace lines from `{% block content %}` through `{% endblock %}` (the content block) with:

```html
{% block content %}

{# ── Page header ──────────────────────────────────────────────────── #}
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

{# ── Search row ───────────────────────────────────────────────────── #}
<div class="search-row">
  <div class="search-box">
    <i data-lucide="search" class="search-box__icon"></i>
    <input type="text" id="search-input" autocomplete="off"
           placeholder="{{ t('list.search_placeholder') }}"
           value="{{ q }}">
    <button type="button" id="search-clear" class="search-box__clear{% if not q %} hidden{% endif %}"
            title="{{ t('list.search_clear') }}">×</button>
  </div>
</div>

{# ── Filter panel (toggle + collapsible body) ─────────────────────── #}
{% set total_active_filters =
    (active_filters.brand | length) +
    (active_filters.condition | length) +
    (active_filters.theme | length) +
    (active_filters.status | length) %}

<div class="filter-panel" id="filter-panel">
  <div class="filter-panel__bar">
    <button type="button" id="filter-toggle" class="filter-toggle">
      <i data-lucide="chevron-right" class="filter-toggle__chevron"></i>
      <span>{{ t('list.filters') }}</span>
      {% if total_active_filters > 0 %}
        <span class="filter-toggle__count">{{ t('list.filters_active', count=total_active_filters) }}</span>
      {% endif %}
    </button>
    {% if total_active_filters > 0 or q %}
      <a href="/" class="filter-clear">{{ t('list.filter_clear_all') }}</a>
    {% endif %}
  </div>

  <div class="filter-panel__body" id="filter-panel-body">
    {% set facet_labels = {
      'brand':     t('list.facet_brand'),
      'condition': t('list.facet_condition'),
      'theme':     t('list.facet_theme'),
      'status':    t('list.facet_status'),
    } %}
    {% for facet_name in ['brand', 'condition', 'theme', 'status'] %}
      {% set counts = facets[facet_name] %}
      {% if counts %}
        <div class="facet-group" data-facet="{{ facet_name }}">
          <div class="facet-group__label">{{ facet_labels[facet_name] }}</div>
          <div class="facet-group__options">
            {% for value, count in counts.items() | sort %}
              {% set is_active = value in active_filters[facet_name] %}
              {% set display_value = (
                t('condition.' ~ value) if facet_name == 'condition'
                else (t('list.status_' ~ value) if facet_name == 'status'
                else value)
              ) %}
              <label class="facet-check{% if is_active %} active{% endif %}">
                <input type="checkbox"
                       name="{{ facet_name }}"
                       value="{{ value }}"
                       {% if is_active %}checked{% endif %}>
                <span class="facet-check__label">{{ display_value }}</span>
                <span class="facet-check__count">({{ count }})</span>
              </label>
            {% endfor %}
          </div>
        </div>
      {% endif %}
    {% endfor %}
  </div>
</div>

{# ── Sort bar ─────────────────────────────────────────────────────── #}
{% if sets or q or total_active_filters > 0 %}
<div class="sort-bar">
  <span class="kicker">{{ t('list.sort_by') }}</span>
  {% set sort_labels = {
    'date_of_purchase': t('list.sort_date'),
    'name':             t('list.sort_name'),
    'brand':            t('list.sort_brand'),
    'part_count':       t('list.sort_parts'),
    'price_paid':       t('list.sort_price'),
  } %}
  {% for col, label in sort_labels.items() %}
    {% set new_dir = 'ASC' if (sort == col and dir == 'DESC') else 'DESC' %}
    <a href="?sort={{ col }}&dir={{ new_dir }}{% if q %}&q={{ q | urlencode }}{% endif %}{% for fname, fvals in active_filters.items() %}{% for fv in fvals %}&{{ fname }}={{ fv | urlencode }}{% endfor %}{% endfor %}"
       class="sort-btn sort-link{% if sort == col %} active {{ dir | lower }}{% endif %}">
      {{ label }}
    </a>
  {% endfor %}
</div>
{% endif %}

{# ── Results region (partial — refreshed by JS on filter changes) ── #}
{% include "_results_partial.html" %}

{% endblock %}
```

This new content block:
- Adds the search row above the sort bar
- Adds the collapsible filter panel
- Preserves the sort bar but carries `q`/filter state in its links
- Replaces the inline set-list/empty-state with `{% include "_results_partial.html" %}`
- Removes the now-unused `cond_class` definition from the parent template (it lives in the partial)

- [ ] **Step 3: Smoke-test in the browser**

Reload `http://localhost:8123/`.

Expected:
- Search input appears between the page header and (now-empty-looking) filter panel
- Filter panel toggle is visible but body is empty until styled (Task 18)
- Sort bar still works
- Set cards render
- No JS errors in the console (the filter checkboxes won't do anything yet — wired in Task 14)

Don't worry about visual styling here — that's Task 18. Just confirm the template renders without Jinja2 errors.

- [ ] **Step 4: Commit**

```
git add templates/index.html
git commit -m "feat(templates): add search row, filter panel, and partial include to index

Search and filter UI is now in the markup but unstyled and unwired
to JS. Sort bar links preserve search and filter state."
```

---

## Phase 4 — Frontend JS (manual verification)

### Task 13: Wire up search debounce, checkbox handlers, and partial swap

**Files:**
- Modify: `templates/index.html` (the `{% block scripts %}` section at the bottom)

- [ ] **Step 1: Replace the `{% block scripts %}` content**

Replace the existing `{% block scripts %}` … `{% endblock %}` block at the bottom of `templates/index.html` with:

```html
{% block scripts %}
<script>
// ── Existing Brickset sync handler ────────────────────────────────────────
async function syncBrickset(id, btn) {
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  const r = await fetch(`/api/sets/${id}/sync-brickset`, { method: 'POST' });
  const data = await r.json();
  lucide.createIcons();
  btn.disabled = false;
  btn.innerHTML = data.status === 'success'
    ? '<i data-lucide="check" style="width:13px;height:13px"></i>'
    : '<i data-lucide="alert-circle" style="width:13px;height:13px"></i>';
  lucide.createIcons();
}

// ── Live search + filter ──────────────────────────────────────────────────
(function () {
  const searchInput = document.getElementById('search-input');
  const searchClear = document.getElementById('search-clear');
  const filterPanel = document.getElementById('filter-panel');

  if (!searchInput || !filterPanel) return;

  let debounceTimer = null;

  function currentQueryString() {
    const params = new URLSearchParams();
    const q = searchInput.value.trim();
    if (q) params.set('q', q);
    filterPanel.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
      params.append(cb.name, cb.value);
    });
    // Preserve sort if present in current URL
    const currentParams = new URLSearchParams(window.location.search);
    if (currentParams.has('sort')) params.set('sort', currentParams.get('sort'));
    if (currentParams.has('dir'))  params.set('dir',  currentParams.get('dir'));
    return params.toString();
  }

  async function applyFilters() {
    const qs = currentQueryString();
    // Update URL (no reload)
    const newUrl = qs ? `/?${qs}` : '/';
    history.replaceState(null, '', newUrl);
    // Fetch the new results partial
    const r = await fetch(`/api/sets/filter${qs ? '?' + qs : ''}`);
    if (!r.ok) return;
    const html = await r.text();
    // Swap the entire #results-region (the partial's outer div has the same id).
    // We re-query each call because the previous div was replaced, not mutated.
    const oldHost = document.getElementById('results-region');
    if (oldHost) {
      const tmp = document.createElement('div');
      tmp.innerHTML = html;
      const fresh = tmp.querySelector('#results-region');
      if (fresh) {
        oldHost.replaceWith(fresh);
        lucide.createIcons();
      }
    }
    if (searchClear) searchClear.classList.toggle('hidden', !searchInput.value);
  }

  // Search input — debounced
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyFilters, 250);
  });

  // Clear search button
  if (searchClear) {
    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      applyFilters();
      searchInput.focus();
    });
  }

  // Checkbox changes — immediate, no debounce
  filterPanel.addEventListener('change', (e) => {
    if (e.target.matches('input[type="checkbox"]')) applyFilters();
  });
})();
</script>
{% endblock %}
```

Notes:
- The IIFE returns early if `#search-input` or `#filter-panel` is missing, so the script is safe even if a future template variation omits them.
- After each swap, we re-run `lucide.createIcons()` so icons in fresh markup render.
- `#results-region` is re-queried inside `applyFilters` rather than cached — because `replaceWith` discards the old node, a cached reference would go stale after the first swap.

- [ ] **Step 2: Manual browser test — search**

1. Reload `http://localhost:8123/`.
2. Type in the search box. After ~250 ms of inactivity, the results region updates.
3. The URL bar reflects `?q=...`.
4. Clear button appears; click it; results return; URL clears.
5. Refresh the page with `?q=...` already in the URL — the search input is pre-filled and results match.

- [ ] **Step 3: Manual browser test — filters**

1. Tick a brand checkbox — results update immediately.
2. URL reflects `?brand=...`.
3. Tick another brand — both in URL, OR semantics in results.
4. Tick a condition — AND with the brand filter.
5. Untick everything — back to full collection, URL clears.

- [ ] **Step 4: Commit**

```
git add templates/index.html
git commit -m "feat(ui): wire live search and filter checkboxes to partial swap

Search input debounced 250ms; checkboxes immediate. URL updated
via history.replaceState — refresh preserves filters."
```

---

### Task 14: Wire up filter-panel toggle with localStorage persistence

**Files:**
- Modify: `templates/index.html` (extend the existing IIFE in `{% block scripts %}`)

- [ ] **Step 1: Add panel toggle logic**

Inside the existing IIFE in `index.html`, just before the closing `})();`, add:

```javascript
// ── Filter panel collapse/expand ──────────────────────────────────────────
const filterToggle = document.getElementById('filter-toggle');
const filterBody   = document.getElementById('filter-panel-body');
const PANEL_KEY    = 'bst_filters_open';

function setPanelOpen(open) {
  filterPanel.classList.toggle('open', open);
  filterBody.style.display = open ? '' : 'none';
  const chev = filterToggle.querySelector('.filter-toggle__chevron');
  if (chev) chev.style.transform = open ? 'rotate(90deg)' : '';
}

// Determine initial state: localStorage, but force open if any filters are active
const hasActiveFilters = filterPanel.querySelectorAll('input[type="checkbox"]:checked').length > 0;
const savedOpen = localStorage.getItem(PANEL_KEY) === '1';
setPanelOpen(savedOpen || hasActiveFilters);

if (filterToggle) {
  filterToggle.addEventListener('click', () => {
    const newOpen = !filterPanel.classList.contains('open');
    setPanelOpen(newOpen);
    localStorage.setItem(PANEL_KEY, newOpen ? '1' : '0');
  });
}
```

- [ ] **Step 2: Manual browser test**

1. Reload `/` with no filters. Panel is closed (or whatever localStorage says).
2. Click "Filters" — body expands, chevron rotates.
3. Reload — state preserved.
4. Close the panel, then load `/?brand=LEGO` — panel auto-opens because a filter is active.
5. The default for a brand-new user (no localStorage) is closed.

- [ ] **Step 3: Commit**

```
git add templates/index.html
git commit -m "feat(ui): collapsible filter panel with localStorage persistence

Auto-opens when filters are active; otherwise honours stored preference.
Default for first-time users is closed."
```

---

## Phase 5 — Polish

### Task 15: Add new i18n keys

**Files:**
- Modify: `locales/de.json`
- Modify: `locales/en.json`

- [ ] **Step 1: Add keys to `locales/en.json`**

Inside the `"list"` object in `locales/en.json`, after the existing keys, add:

```json
    "search_placeholder": "Search across all fields...",
    "search_clear":       "Clear search",
    "filters":            "Filters",
    "filters_active":     "{count} active",
    "filter_clear_all":   "Clear all filters",
    "facet_brand":        "Brand",
    "facet_condition":    "Condition",
    "facet_theme":        "Theme",
    "facet_status":       "Status",
    "status_complete":    "Complete",
    "status_draft":       "Draft",
    "results_count":      "{shown} of {total} sets",
    "no_matches":         "No sets match these filters"
```

Make sure the previous key in the block ends with a comma so JSON stays valid.

- [ ] **Step 2: Add keys to `locales/de.json`**

Inside the `"list"` object in `locales/de.json`, add the same keys with German values:

```json
    "search_placeholder": "Alle Felder durchsuchen...",
    "search_clear":       "Suche löschen",
    "filters":            "Filter",
    "filters_active":     "{count} aktiv",
    "filter_clear_all":   "Alle Filter zurücksetzen",
    "facet_brand":        "Marke",
    "facet_condition":    "Zustand",
    "facet_theme":        "Thema",
    "facet_status":       "Status",
    "status_complete":    "Vollständig",
    "status_draft":       "Entwurf",
    "results_count":      "{shown} von {total} Sets",
    "no_matches":         "Keine Sets entsprechen diesen Filtern"
```

- [ ] **Step 3: Validate JSON**

Run:
```
.venv/bin/python -c "import json; json.load(open('locales/en.json')); json.load(open('locales/de.json')); print('OK')"
```
Expected: `OK`.

- [ ] **Step 4: Reload browser and verify**

Open `http://localhost:8123/` in both languages. Confirm: search placeholder, filter labels, facet group labels, condition translations, result-count line, and the "no matches" empty state all show in the correct language.

- [ ] **Step 5: Commit**

```
git add locales/en.json locales/de.json
git commit -m "feat(i18n): add search and filter translation keys

13 new keys covering search placeholder, filter labels, facet
group names, result count, and the filtered-empty state."
```

---

### Task 16: Add CSS for search and filter UI

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Bump the cache-buster version in `templates/base.html`**

Open `templates/base.html`, find the line with `style.css?v=2`, and change it to `?v=3`. (If the version is different, increment it.)

- [ ] **Step 2: Append new styles to `static/style.css`**

Append at the end of `static/style.css`:

```css
/* ---------- Search Row --------------------------------------------- */
.search-row {
  margin-bottom: var(--sp-4);
}
.search-box {
  position: relative;
  display: flex;
  align-items: center;
}
.search-box__icon {
  position: absolute;
  left: 12px;
  width: 16px;
  height: 16px;
  color: var(--fg-muted);
  pointer-events: none;
}
.search-box input {
  width: 100%;
  font: 400 15px/1.4 var(--font-body);
  color: var(--fg);
  background: var(--weiss);
  border: 1px solid rgba(27,58,92,.28);
  border-radius: var(--r-md);
  padding: 10px 36px 10px 36px;
  outline: none;
  transition: border-color var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast) var(--ease-out);
}
.search-box input:focus {
  border-color: var(--kuestenblau);
  box-shadow: 0 0 0 3px rgba(58,124,165,.18);
}
.search-box__clear {
  position: absolute;
  right: 8px;
  width: 22px;
  height: 22px;
  border: none;
  background: var(--bg-card);
  color: var(--fg-muted);
  border-radius: 50%;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.search-box__clear:hover { background: var(--altes-papier); color: var(--fg); }

/* ---------- Filter Panel ------------------------------------------- */
.filter-panel {
  margin-bottom: var(--sp-4);
}
.filter-panel__bar {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding-bottom: var(--sp-2);
}
.filter-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font: 500 12px/1 var(--font-body);
  letter-spacing: .04em;
  text-transform: uppercase;
  color: var(--fg-heading);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 0;
}
.filter-toggle__chevron {
  width: 14px;
  height: 14px;
  transition: transform var(--dur-fast) var(--ease-out);
}
.filter-toggle__count {
  font: 500 11px/1 var(--font-mono);
  color: var(--kuestenblau);
  background: rgba(58,124,165,.12);
  padding: 2px 8px;
  border-radius: var(--r-pill);
  text-transform: none;
  letter-spacing: 0;
}
.filter-clear {
  font: 400 12px/1 var(--font-body);
  color: var(--fg-muted);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
}
.filter-clear:hover { color: var(--accent); }

.filter-panel__body {
  background: var(--bg-card);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  padding: var(--sp-3) var(--sp-4);
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-4) var(--sp-5);
}
.facet-group { min-width: 0; }
.facet-group__label {
  font: 500 10px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--sp-2);
}
.facet-group__options {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}
.facet-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 400 12px/1 var(--font-body);
  color: var(--fg);
  background: var(--weiss);
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
  padding: 5px 10px 5px 8px;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out);
}
.facet-check input[type="checkbox"] {
  width: 12px;
  height: 12px;
  margin: 0;
  accent-color: var(--kuestenblau);
  cursor: pointer;
}
.facet-check__count {
  color: var(--fg-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}
.facet-check:hover { border-color: var(--rule-strong); }
.facet-check.active {
  background: rgba(58,124,165,.10);
  border-color: var(--kuestenblau);
}
.facet-check.active .facet-check__count { color: var(--kuestenblau); }

/* ---------- Result Count Line -------------------------------------- */
.results-count {
  font: 400 12px/1.4 var(--font-mono);
  color: var(--fg-muted);
  margin-bottom: var(--sp-3);
}
.results-count i { color: var(--fg-muted); }
```

- [ ] **Step 3: Reload the browser**

Open `http://localhost:8123/`. Verify visually:
- Search box: rounded input with a magnifier icon on the left and (when text is present) a clear-X on the right
- Filter panel: tight bar with a chevron + "Filters" label; clicking expands a card with facet groups
- Facet checkboxes: pill-shaped, ticked state has accent colour
- Result count appears above cards when filtering
- No layout regressions on cards / sort bar

- [ ] **Step 4: Commit**

```
git add static/style.css templates/base.html
git commit -m "style: add search/filter UI styles + bump CSS cache buster

Pill-shaped facet checkboxes with active state in the accent
colour. Filter panel card matches existing design tokens
(kartenpapier/tiefwasser/kuestenblau palette)."
```

---

### Task 17: Final end-to-end manual verification

**Files:** none modified.

This is a deliberate manual sweep before declaring Iteration 3 done. Walk through each scenario in `http://localhost:8123/` in both DE and EN.

- [ ] **Step 1: Search behaviour**
  - Type partial set name → debounced narrow
  - Type a set number → matches
  - Type an umlaut (e.g. `möbel` if you have one) → case-insensitive match
  - Type something that matches nothing → "No sets match these filters" appears + Clear all link
  - Clear → back to full collection
  - Refresh while `?q=...` is in URL → search input pre-filled, results match

- [ ] **Step 2: Filter behaviour**
  - Tick a brand → results narrow, URL updates
  - Tick a second brand → OR within facet
  - Tick a condition while brands are still ticked → AND across facets
  - Untick → results widen
  - "Clear all filters" link → everything reset
  - Reload with `?brand=LEGO&condition=gebaut` → checkboxes pre-checked, results match

- [ ] **Step 3: Faceted counts**
  - Tick LEGO → brand facet still shows BlueBrixx with a count (own-filter-excluded)
  - Tick LEGO → condition facet only shows conditions present in LEGO sets
  - Add a draft to your collection → status facet shows "Draft (1)"

- [ ] **Step 4: Filter panel toggle**
  - Fresh browser session: panel is collapsed
  - Open panel → reload → still open
  - Close panel → reload → still closed
  - Close panel → load `/?brand=LEGO` → panel auto-opens (because filters are active)

- [ ] **Step 5: Sort + filter interaction**
  - Apply filters → click a sort button → URL keeps `?q=...&brand=...&sort=name&dir=ASC`
  - Click again → direction flips, filters preserved
  - Search/filter changes after sorting preserve the chosen sort

- [ ] **Step 6: Language switch**
  - Switch DE ↔ EN → filtered view preserved (existing `next` mechanism); facet labels / placeholders translate

- [ ] **Step 7: Empty states**
  - With a populated collection: filter to zero → "No matches" + Clear all
  - On a fresh DB (or temporarily rename `data/brickset.db`): "No sets yet" + Add Set button
  - Restore DB after verifying.

- [ ] **Step 8: Existing functionality unaffected**
  - Click pencil → edit flow still works, save returns to filtered view (or `/`)
  - Click trash → delete confirmation still works
  - Brickset sync button on LEGO sets still works
  - `/add` still works end-to-end

- [ ] **Step 9: Commit a verification marker**

```
git commit --allow-empty -m "chore: verify Iteration 3 end-to-end

All scenarios in the implementation plan's Task 17 checklist
pass in both DE and EN."
```

---

## Done

Iteration 3 complete. The collection list now supports:

- Live, case-insensitive substring search across all text-ish fields (Unicode-aware via `py_lower`)
- Multi-select filter facets for brand, condition, theme, status (OR within, AND across)
- Dynamic facet counts that respect other filters but not their own (so checkboxes stay switchable)
- URL state via `history.replaceState` → bookmarking, back button, refresh all preserve view
- Collapsible filter panel with `localStorage` persistence, auto-open when filters are active
- Distinct empty states for "collection genuinely empty" vs. "filters exclude everything"
- Bilingual (DE/EN) throughout

Backend has full pytest coverage (search, filters, facets, count). Frontend verification was manual; backfilling tests for Iterations 1+2 is tracked in `MEMORY/task_plan.md`.

Next iterations on the V1 path: **Iteration 4 (details view) → code review → Phase T (LaunchAgent deployment)**.
