# Brand Slug Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `BRAND_SLUGS` dict with a user-configurable SQLite-backed table managed via a new `/settings/brand-slugs` settings page; auto-populate the table whenever a merlinssteine.de scrape succeeds.

**Architecture:** New `execution/brand_slugs.py` module exposes DB-backed CRUD helpers plus `brand_to_slug()` (relocated from scraper.py). New `brand_slugs` table seeded from the existing hardcoded dict via `INSERT OR IGNORE` in `init_db()`. Four new routes for the settings page (GET list + POST add/update/delete). Gear icon in the site header links to `/settings/brand-slugs`. Inline edit on the slug column via small fetch-based JS.

**Tech Stack:** FastAPI 0.115, Starlette 0.46, Jinja2 3.1, SQLite (stdlib `sqlite3`), pytest with TestClient.

**Spec:** `docs/superpowers/specs/2026-05-17-brand-slugs-config-design.md`

---

## Phase 0 — Backend (TDD)

### Task 1: Migration in `init_db()` — create + seed `brand_slugs` table

**Files:**
- Modify: `execution/db.py` (extend `init_db()`)
- Create: `tests/test_brand_slugs_schema.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_brand_slugs_schema.py`:
```python
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
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_brand_slugs_schema.py -v`
Expected: `test_brand_slugs_table_exists` and `test_brand_slugs_seeded_from_dict` fail with "no such table: brand_slugs". The other two also fail (no table to UPDATE / INSERT into).

- [ ] **Step 3: Update `init_db()` in `execution/db.py`**

Read the file to see the current shape. Inside `init_db()`, AFTER the existing `executescript(...)` block and AFTER the `try: conn.execute("ALTER TABLE sets ADD COLUMN list_price REAL")` block (which was added in Iteration 3.7), add:

```python
        # ── brand_slugs table (Iteration 4.5) ────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_slugs (
                brand      TEXT PRIMARY KEY,
                slug       TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Seed from the existing hardcoded dict. INSERT OR IGNORE ensures
        # this is idempotent and never overwrites user-edited rows.
        from execution.scraper import BRAND_SLUGS
        for brand, slug in BRAND_SLUGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO brand_slugs (brand, slug) VALUES (?, ?)",
                (brand, slug),
            )
```

Place this block inside the existing `with get_connection() as conn:` so it runs in the same DB session.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_brand_slugs_schema.py -v`
Expected: 4 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 109 passed (105 prior + 4 new).

- [ ] **Step 5: Commit**

```
git add execution/db.py tests/test_brand_slugs_schema.py
git commit -m "$(cat <<'EOF'
feat(db): add brand_slugs table + seed from BRAND_SLUGS dict

The hardcoded BRAND_SLUGS dict becomes seed data for a new SQLite
table. INSERT OR IGNORE ensures the migration is idempotent and
never overwrites user edits on subsequent app starts.
EOF
)"
```

---

### Task 2: New module `execution/brand_slugs.py` with all 6 functions

**Files:**
- Create: `execution/brand_slugs.py`
- Create: `tests/test_brand_slugs.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_brand_slugs.py`:
```python
"""brand_slugs module: CRUD helpers + brand_to_slug() with DB-backed lookup."""
import pytest
import sqlite3

from execution.brand_slugs import (
    brand_to_slug,
    list_brand_slugs,
    add_brand_slug,
    ensure_brand_slug,
    update_brand_slug,
    delete_brand_slug,
)


# ── brand_to_slug ──────────────────────────────────────────────────────────

def test_brand_to_slug_returns_seeded_value(db):
    assert brand_to_slug("LEGO") == "lego"
    assert brand_to_slug("Pantasy") == "pant"


def test_brand_to_slug_normalises_input(db):
    assert brand_to_slug("  LEGO  ") == "lego"
    assert brand_to_slug("PANTASY") == "pant"
    assert brand_to_slug("BlueBrixx") == "bb"


def test_brand_to_slug_falls_back_for_unknown(db):
    assert brand_to_slug("Some New Brand") == "some-new-brand"
    assert brand_to_slug("Ikea") == "ikea"


# ── list_brand_slugs ───────────────────────────────────────────────────────

def test_list_brand_slugs_returns_sorted_pairs(db):
    pairs = list_brand_slugs()
    brands = [p["brand"] for p in pairs]
    assert brands == sorted(brands)
    assert len(pairs) >= 8  # at least the seed entries


# ── add_brand_slug ─────────────────────────────────────────────────────────

def test_add_brand_slug_inserts(db):
    add_brand_slug("Foo Brand", "foo")
    assert brand_to_slug("foo brand") == "foo"


def test_add_brand_slug_normalises(db):
    add_brand_slug("  IKEA  ", "  IK  ")
    assert brand_to_slug("ikea") == "ik"


def test_add_brand_slug_duplicate_raises(db):
    with pytest.raises(sqlite3.IntegrityError):
        add_brand_slug("LEGO", "different-slug")


# ── ensure_brand_slug ──────────────────────────────────────────────────────

def test_ensure_brand_slug_inserts_when_missing(db):
    ensure_brand_slug("Foo", "f")
    assert brand_to_slug("foo") == "f"


def test_ensure_brand_slug_noop_when_present(db):
    """ensure_brand_slug never overwrites an existing seeded value."""
    ensure_brand_slug("LEGO", "different-slug")
    assert brand_to_slug("lego") == "lego"  # original seed wins


# ── update_brand_slug ──────────────────────────────────────────────────────

def test_update_brand_slug_changes_slug(db):
    update_brand_slug("LEGO", "LG")
    assert brand_to_slug("lego") == "lg"


def test_update_brand_slug_for_missing_brand_is_noop(db):
    """No exception, no row created."""
    update_brand_slug("NonexistentBrand", "x")
    assert brand_to_slug("nonexistentbrand") == "nonexistentbrand"  # fallback


# ── delete_brand_slug ──────────────────────────────────────────────────────

def test_delete_brand_slug_removes_row(db):
    delete_brand_slug("LEGO")
    assert brand_to_slug("lego") == "lego"  # falls back to default


def test_delete_brand_slug_for_missing_brand_is_noop(db):
    delete_brand_slug("NonexistentBrand")  # must not raise
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_brand_slugs.py -v`
Expected: ImportError on `execution.brand_slugs` (module doesn't exist).

- [ ] **Step 3: Create `execution/brand_slugs.py`**

Write the new file:
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
```

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_brand_slugs.py -v`
Expected: 13 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 122 passed (109 prior + 13 new).

- [ ] **Step 5: Commit**

```
git add execution/brand_slugs.py tests/test_brand_slugs.py
git commit -m "$(cat <<'EOF'
feat(brand_slugs): add CRUD module with brand_to_slug + helpers

New execution/brand_slugs.py exposes brand_to_slug() (DB-backed),
list_brand_slugs, add_brand_slug, ensure_brand_slug (idempotent
INSERT OR IGNORE), update_brand_slug, delete_brand_slug. All input
normalised (lowercased + trimmed) to match the seed data shape.
EOF
)"
```

---

### Task 3: Migrate callers + auto-populate hook + remove old `brand_to_slug` from scraper

**Files:**
- Modify: `execution/scraper.py` (remove `brand_to_slug` function; keep `BRAND_SLUGS` dict with a new comment)
- Modify: `navigation/lookup_router.py` (update import; call `ensure_brand_slug` after successful scrape)
- Modify: `main.py` (update lazy import in `details_page`)
- Create: `tests/test_auto_populate_brand_slug.py`

- [ ] **Step 1: Write the failing test for auto-populate**

Write `tests/test_auto_populate_brand_slug.py`:
```python
"""After a successful merlinssteine scrape, the (brand, slug) pair is
auto-persisted to brand_slugs via ensure_brand_slug. New brands whose
name IS the slug end up visible in /settings/brand-slugs automatically."""
import httpx
import pytest

from execution import scraper, brand_slugs
from navigation import lookup_router


class _FakeResponse:
    def __init__(self, html: str, status: int = 200):
        self.text = html
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _FakeClient:
    _html: str = ""
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def get(self, url, headers=None, follow_redirects=True):
        return _FakeResponse(_FakeClient._html)


_HTML_SUCCESS = """
<html><body>
<h1>Ikea - Some Item | Set 99999</h1>
<h2>Details</h2>
<ul>
  <li>Von: Ikea</li>
  <li>Setnummer: 99999</li>
</ul>
<ul><li>500 Teile</li></ul>
</body></html>
"""


@pytest.fixture
def fake_scrape(monkeypatch, db):
    _FakeClient._html = _HTML_SUCCESS
    monkeypatch.setattr(scraper.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(scraper, "check_quota", lambda svc: True)
    monkeypatch.setattr(scraper, "increment_quota", lambda svc: None)


async def test_successful_scrape_auto_populates_brand_slugs(fake_scrape):
    """A brand the scraper hasn't seen before becomes visible in brand_slugs
    after a successful lookup."""
    # Confirm "Ikea" is NOT in brand_slugs initially
    assert "ikea" not in {r["brand"] for r in brand_slugs.list_brand_slugs()}

    result = await lookup_router._flow1(brand="Ikea", set_number="99999")
    assert result["status"] == "success"

    # Now "ikea" SHOULD be in the table with the fallback-derived slug "ikea"
    pairs = {r["brand"]: r["slug"] for r in brand_slugs.list_brand_slugs()}
    assert "ikea" in pairs
    assert pairs["ikea"] == "ikea"


async def test_successful_scrape_does_not_overwrite_existing_slug(fake_scrape):
    """If the brand is already mapped, ensure_brand_slug leaves it alone."""
    # Seed a custom mapping
    brand_slugs.add_brand_slug("CustomBrand", "custom-existing-slug")
    # Run the scrape — slug computed for CustomBrand would be "custombrand" (fallback)
    await lookup_router._flow1(brand="CustomBrand", set_number="12345")
    # The existing slug must NOT be overwritten
    assert brand_slugs.brand_to_slug("custombrand") == "custom-existing-slug"
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_auto_populate_brand_slug.py -v`
Expected: ImportError on `execution.brand_slugs` if it doesn't exist yet (but Task 2 added it). The actual test failure mode: the first test will fail because `lookup_router` doesn't call `ensure_brand_slug` yet — `brand_slugs.list_brand_slugs()` won't contain "ikea" after the scrape.

- [ ] **Step 3: Remove `brand_to_slug` from `execution/scraper.py`**

Read `execution/scraper.py`. Find this block (around lines 17-34):

```python
BRAND_SLUGS: dict[str, str] = {
    "bluebrixx":  "bb",
    "blue brixx": "bb",
    "lego":       "lego",
    "cobi":       "cobi",
    "mould king": "mk",
    "cada":       "cada",
    "lumibricks": "lumi",
    "funwhole":   "lumi",   # Lumibricks former name
    "pantasy":    "pant",
}

UA = "BricksetTracker/1.0 (personal collection tool; single-user)"
BASE = "https://www.merlinssteine.de"


def brand_to_slug(brand: str) -> str:
    return BRAND_SLUGS.get(brand.lower().strip(), brand.lower().strip().replace(" ", "-"))
```

Replace it with:

```python
# Seed data for the brand_slugs table. Read at app startup by init_db()
# via INSERT OR IGNORE; not used at request time. See execution/brand_slugs.py
# for the runtime lookup.
BRAND_SLUGS: dict[str, str] = {
    "bluebrixx":  "bb",
    "blue brixx": "bb",
    "lego":       "lego",
    "cobi":       "cobi",
    "mould king": "mk",
    "cada":       "cada",
    "lumibricks": "lumi",
    "funwhole":   "lumi",   # Lumibricks former name
    "pantasy":    "pant",
}

UA = "BricksetTracker/1.0 (personal collection tool; single-user)"
BASE = "https://www.merlinssteine.de"
```

(The `brand_to_slug` function is deleted; the dict stays as documented seed data.)

- [ ] **Step 4: Update `navigation/lookup_router.py`**

Read the file. Find the import line (around line 9):
```python
from execution.scraper import brand_to_slug, scrape_set
```
Replace with:
```python
from execution.scraper import scrape_set
from execution.brand_slugs import brand_to_slug, ensure_brand_slug
```

Then find `_flow1` (around line 62). After the `if ms_succeeded:` block (which currently merges the result and writes to ean_cache), add the `ensure_brand_slug` call. The current shape is:

```python
    # ── merlinssteine.de scrape ─────────────────────────────────────
    ms_result    = await scrape_set(slug, set_number)
    ms_succeeded = ms_result["status"] == "success"

    if ms_succeeded:
        _merge_from_merlinssteine(prefill, ms_result)
        if ms_result.get("ean") and not ean:
            _ean_cache_write(ms_result["ean"], prefill["brand"], set_number, "merlinssteine")
```

Add `ensure_brand_slug` immediately inside the success block:

```python
    if ms_succeeded:
        _merge_from_merlinssteine(prefill, ms_result)
        if ms_result.get("ean") and not ean:
            _ean_cache_write(ms_result["ean"], prefill["brand"], set_number, "merlinssteine")
        # Auto-populate brand_slugs so future settings-page browsing reflects
        # every brand the user has successfully used. Idempotent — no-op for
        # already-known brands.
        ensure_brand_slug(brand, slug)
```

- [ ] **Step 5: Update `main.py`**

Find the `details_page` route. Inside its body there's a lazy import:
```python
    from execution.scraper import brand_to_slug
```
Change to:
```python
    from execution.brand_slugs import brand_to_slug
```

- [ ] **Step 6: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_auto_populate_brand_slug.py -v`
Expected: 2 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 124 passed (122 prior + 2 new).

If any existing test (e.g., `test_scraper_list_price.py`, `test_lookup_router_list_price.py`, route tests in `test_details_route.py`) breaks because they import `brand_to_slug` from `execution.scraper`, fix those imports too.

- [ ] **Step 7: Commit**

```
git add execution/scraper.py navigation/lookup_router.py main.py tests/test_auto_populate_brand_slug.py
git commit -m "$(cat <<'EOF'
feat(lookup): switch brand_to_slug to DB + auto-populate on scrape success

brand_to_slug() now reads from the brand_slugs table (Iteration 4.5)
instead of the hardcoded dict. The dict in scraper.py stays as seed
data for fresh installs.

After every successful merlinssteine scrape, ensure_brand_slug()
persists the (brand, slug) pair via INSERT OR IGNORE. Net effect:
new brands whose name IS the slug appear in the settings page
automatically; user-edited custom mappings (Pantasy → pant, etc.)
are never overwritten.
EOF
)"
```

---

## Phase 1 — Settings page (routes + tests)

### Task 4: `GET /settings/brand-slugs` page route + minimal template

**Files:**
- Modify: `main.py` (add new route)
- Create: `templates/settings_brand_slugs.html` (minimal stub — Task 7 fleshes out)
- Create: `tests/test_settings_routes.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_settings_routes.py`:
```python
"""Smoke tests for the settings/brand-slugs routes."""
from fastapi.testclient import TestClient
from main import app


def test_settings_page_renders(db):
    client = TestClient(app)
    r = client.get("/settings/brand-slugs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # Seeded brands must be visible
    assert "lego" in r.text
    assert "pantasy" in r.text
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_settings_routes.py -v`
Expected: 404 (route doesn't exist yet).

- [ ] **Step 3: Create minimal `templates/settings_brand_slugs.html`**

```html
{% extends "base.html" %}
{% block title %}{{ t('settings.brand_slugs.title') }} · Brickset Tracker{% endblock %}
{% block header_title %}{{ t('settings.brand_slugs.title') }}{% endblock %}

{% block content %}
<h1>{{ t('settings.brand_slugs.title') }}</h1>
<table>
  <thead>
    <tr><th>{{ t('settings.brand_slugs.col_brand') }}</th>
        <th>{{ t('settings.brand_slugs.col_slug') }}</th></tr>
  </thead>
  <tbody>
    {% for pair in pairs %}
    <tr><td>{{ pair.brand }}</td><td>{{ pair.slug }}</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

This minimal stub is enough for the Task 4 test to pass. Task 7 replaces it with the full page.

- [ ] **Step 4: Add the route to `main.py`**

Find a good location (after the existing `import_page` / `api_import_*` routes, before the API section). Add:

```python
@app.get("/settings/brand-slugs", response_class=HTMLResponse)
async def settings_brand_slugs(
    request: Request,
    error: str | None = None,
    brand: str | None = None,
):
    """Brand → merlinssteine.de URL slug mappings (settings)."""
    from execution.brand_slugs import list_brand_slugs
    pairs = list_brand_slugs()
    return templates.TemplateResponse(request, "settings_brand_slugs.html", context=_ctx(
        request, pairs=pairs,
        error=error, error_brand=brand,
    ))
```

The `error` and `brand` query params are populated by the redirect from `/add` / `/update` / `/delete` routes (Task 5) when a validation error occurs.

- [ ] **Step 5: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_settings_routes.py -v`
Expected: 1 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 125 passed (124 prior + 1 new).

- [ ] **Step 6: Commit**

```
git add main.py templates/settings_brand_slugs.html tests/test_settings_routes.py
git commit -m "$(cat <<'EOF'
feat(routes): add GET /settings/brand-slugs stub page

Minimum viable page listing brand→slug pairs from the new
brand_slugs table. Subsequent tasks add the add/update/delete POST
routes, the full template, inline edit JS, and the gear-icon link
in the site header.
EOF
)"
```

---

### Task 5: POST routes — add, update, delete

**Files:**
- Modify: `main.py` (add three POST routes)
- Modify: `tests/test_settings_routes.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_settings_routes.py`**

```python
def test_add_route_inserts_and_redirects(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/add",
                    data={"brand": "Ikea", "slug": "ikea-store"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"

    from execution.brand_slugs import brand_to_slug
    assert brand_to_slug("ikea") == "ikea-store"


def test_add_route_duplicate_returns_error_redirect(db):
    """Inserting a brand that already exists redirects with ?error=duplicate&brand=…"""
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/add",
                    data={"brand": "LEGO", "slug": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    loc = r.headers["location"]
    assert "error=duplicate" in loc
    assert "brand=lego" in loc.lower()


def test_add_route_empty_returns_error_redirect(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/add",
                    data={"brand": "  ", "slug": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "error=empty" in r.headers["location"]


def test_update_route_changes_slug(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/lego/update",
                    data={"slug": "lg"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"
    from execution.brand_slugs import brand_to_slug
    assert brand_to_slug("lego") == "lg"


def test_update_route_unknown_brand_redirects_silently(db):
    """No row exists → no-op + redirect to settings page."""
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/nonexistent/update",
                    data={"slug": "x"},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"


def test_update_route_empty_slug_returns_error_redirect(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/lego/update",
                    data={"slug": "  "},
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "error=empty" in r.headers["location"]


def test_delete_route_removes_row_and_redirects(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/lego/delete",
                    follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/settings/brand-slugs"
    from execution.brand_slugs import brand_to_slug
    assert brand_to_slug("lego") == "lego"  # falls back to default


def test_delete_route_unknown_brand_redirects_silently(db):
    client = TestClient(app)
    r = client.post("/settings/brand-slugs/nonexistent/delete",
                    follow_redirects=False)
    assert r.status_code in (302, 303)
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_settings_routes.py -v`
Expected: 8 tests fail with 404/405 on the new endpoints.

- [ ] **Step 3: Add the three POST routes to `main.py`**

After the GET route from Task 4, append:

```python
@app.post("/settings/brand-slugs/add")
async def settings_brand_slugs_add(
    brand: str = Form(...),
    slug: str = Form(...),
):
    """Add a new brand → slug mapping. Redirects back to the settings page."""
    import sqlite3
    from execution.brand_slugs import add_brand_slug

    brand_clean = brand.strip()
    slug_clean = slug.strip()
    if not brand_clean or not slug_clean:
        return RedirectResponse(
            "/settings/brand-slugs?error=empty",
            status_code=303,
        )
    try:
        add_brand_slug(brand_clean, slug_clean)
    except sqlite3.IntegrityError:
        return RedirectResponse(
            f"/settings/brand-slugs?error=duplicate&brand={brand_clean.lower()}",
            status_code=303,
        )
    return RedirectResponse("/settings/brand-slugs", status_code=303)


@app.post("/settings/brand-slugs/{brand}/update")
async def settings_brand_slugs_update(
    brand: str,
    slug: str = Form(...),
):
    """Update the slug for an existing brand. Silent no-op if brand doesn't exist."""
    from execution.brand_slugs import update_brand_slug

    slug_clean = slug.strip()
    if not slug_clean:
        return RedirectResponse(
            "/settings/brand-slugs?error=empty",
            status_code=303,
        )
    update_brand_slug(brand, slug_clean)
    return RedirectResponse("/settings/brand-slugs", status_code=303)


@app.post("/settings/brand-slugs/{brand}/delete")
async def settings_brand_slugs_delete(brand: str):
    """Remove a brand → slug mapping. Silent no-op if brand doesn't exist."""
    from execution.brand_slugs import delete_brand_slug
    delete_brand_slug(brand)
    return RedirectResponse("/settings/brand-slugs", status_code=303)
```

`Form` and `RedirectResponse` are already imported at the top of `main.py`. The lazy `from execution.brand_slugs import ...` matches the project's existing pattern of lazy imports inside route handlers.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_settings_routes.py -v`
Expected: 9 passed (1 prior + 8 new).

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 133 passed (125 prior + 8 new).

- [ ] **Step 5: Commit**

```
git add main.py tests/test_settings_routes.py
git commit -m "$(cat <<'EOF'
feat(routes): add POST add/update/delete for brand-slugs

Three new routes: /settings/brand-slugs/add (Form-encoded
brand+slug, 303 redirect, duplicate → ?error=duplicate&brand=…),
/{brand}/update (Form-encoded slug, silent no-op if missing),
/{brand}/delete (silent no-op if missing). All redirect to the
settings page; the page renders the error query params as a
callout banner (Task 7).
EOF
)"
```

---

### Task 6: i18n keys for the settings page

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/de.json`

- [ ] **Step 1: Add `nav.settings` to both files**

In `locales/en.json`, find the existing `"nav"` object (top-level). Append `"settings"` to its keys (preserve comma rules):

```json
    "settings":        "Settings",
```

In `locales/de.json`, same:

```json
    "settings":        "Einstellungen",
```

- [ ] **Step 2: Add `settings.brand_slugs.*` block to `locales/en.json`**

Add a new top-level `"settings"` object (place it after `"import"`, before `"quota"` — alphabetical-ish and logically grouped):

```json
  "settings": {
    "brand_slugs": {
      "title":           "Brand Slugs",
      "intro":           "Maps brand names to merlinssteine.de URL slugs. Brands not in this list use the brand name itself (lowercased, spaces replaced with hyphens).",
      "add_heading":     "Add new",
      "col_brand":       "Brand",
      "col_slug":        "Slug",
      "add_button":      "Add",
      "empty":           "No brand slugs configured yet. Add the first one above.",
      "error_duplicate": "Brand \"{brand}\" already has a slug. Edit the existing row instead.",
      "error_empty":     "Brand and slug must both be non-empty.",
      "delete_confirm":  "Really delete the slug mapping for \"{brand}\"?",
      "save":            "Save",
      "cancel":          "Cancel"
    }
  },
```

- [ ] **Step 3: Same block in `locales/de.json`**

```json
  "settings": {
    "brand_slugs": {
      "title":           "Marken-Slugs",
      "intro":           "Ordnet Markennamen den merlinssteine.de-URL-Slugs zu. Marken, die hier nicht aufgeführt sind, verwenden den Markennamen direkt (kleingeschrieben, Leerzeichen werden zu Bindestrichen).",
      "add_heading":     "Neu hinzufügen",
      "col_brand":       "Marke",
      "col_slug":        "Slug",
      "add_button":      "Hinzufügen",
      "empty":           "Noch keine Marken-Slugs konfiguriert. Füge oben den ersten hinzu.",
      "error_duplicate": "Marke \"{brand}\" hat bereits einen Slug. Bearbeite stattdessen den vorhandenen Eintrag.",
      "error_empty":     "Marke und Slug dürfen nicht leer sein.",
      "delete_confirm":  "Slug-Zuordnung für \"{brand}\" wirklich löschen?",
      "save":            "Speichern",
      "cancel":          "Abbrechen"
    }
  },
```

- [ ] **Step 4: Validate JSON parity**

Run:
```
.venv/bin/python -c "
import json
en = json.load(open('locales/en.json'))
de = json.load(open('locales/de.json'))
assert 'settings' in en['nav'] and 'settings' in de['nav']
assert set(en['settings']['brand_slugs'].keys()) == set(de['settings']['brand_slugs'].keys())
assert len(en['settings']['brand_slugs']) == 12
print('OK', len(en['settings']['brand_slugs']))
"
```
Expected: `OK 12`.

- [ ] **Step 5: Verify tests still green**

Run: `.venv/bin/pytest -v`
Expected: 133 passed.

- [ ] **Step 6: Commit**

```
git add locales/en.json locales/de.json
git commit -m "$(cat <<'EOF'
feat(i18n): add brand-slugs settings translation keys

12 new keys under settings.brand_slugs.* + nav.settings for the
gear icon. EN and DE in parity.
EOF
)"
```

---

## Phase 2 — UI polish

### Task 7: Full settings template (replace minimal stub)

**Files:**
- Modify: `templates/settings_brand_slugs.html` (overwrite the Task 4 stub)

- [ ] **Step 1: Overwrite the template**

Replace the contents with the full page:

```html
{% extends "base.html" %}
{% block title %}{{ t('settings.brand_slugs.title') }} · Brickset Tracker{% endblock %}
{% block header_title %}{{ t('settings.brand_slugs.title') }}{% endblock %}

{% block content %}

<div class="page-header">
  <h1>{{ t('settings.brand_slugs.title') }}</h1>
</div>

<p class="settings-intro">{{ t('settings.brand_slugs.intro') }}</p>

{# ── Error banner ────────────────────────────────────────────────── #}
{% if error == "duplicate" %}
<div class="callout callout-error">
  <span class="callout__mark">×</span>
  <p>{{ t('settings.brand_slugs.error_duplicate', brand=error_brand or '') }}</p>
</div>
{% elif error == "empty" %}
<div class="callout callout-error">
  <span class="callout__mark">×</span>
  <p>{{ t('settings.brand_slugs.error_empty') }}</p>
</div>
{% endif %}

{# ── Add form ────────────────────────────────────────────────────── #}
<div class="settings-section">
  <h2 class="settings-section__heading">{{ t('settings.brand_slugs.add_heading') }}</h2>
  <form method="post" action="/settings/brand-slugs/add" class="brand-slug-add-form">
    <div class="field">
      <label for="add-brand">{{ t('settings.brand_slugs.col_brand') }}</label>
      <input type="text" id="add-brand" name="brand" required>
    </div>
    <div class="field">
      <label for="add-slug">{{ t('settings.brand_slugs.col_slug') }}</label>
      <input type="text" id="add-slug" name="slug" required>
    </div>
    <button type="submit" class="btn btn-primary">
      <i data-lucide="plus" style="width:15px;height:15px"></i>
      {{ t('settings.brand_slugs.add_button') }}
    </button>
  </form>
</div>

{# ── List table ──────────────────────────────────────────────────── #}
{% if pairs %}
<table class="brand-slug-table">
  <thead>
    <tr>
      <th>{{ t('settings.brand_slugs.col_brand') }}</th>
      <th>{{ t('settings.brand_slugs.col_slug') }}</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for pair in pairs %}
    <tr data-brand="{{ pair.brand }}">
      <td class="brand-slug-table__brand">{{ pair.brand }}</td>
      <td class="brand-slug-table__slug">
        <span class="brand-slug-table__slug-display">{{ pair.slug }}</span>
        <input type="text" class="brand-slug-table__slug-input hidden"
               value="{{ pair.slug }}" data-original="{{ pair.slug }}">
      </td>
      <td class="brand-slug-table__actions">
        <button type="button" class="btn btn-ghost btn-sm brand-slug-edit-btn"
                title="{{ t('edit.title') }}">
          <i data-lucide="pencil" style="width:13px;height:13px"></i>
        </button>
        <button type="button" class="btn btn-ghost btn-sm brand-slug-save-btn hidden"
                title="{{ t('settings.brand_slugs.save') }}">
          <i data-lucide="check" style="width:13px;height:13px"></i>
        </button>
        <button type="button" class="btn btn-ghost btn-sm brand-slug-cancel-btn hidden"
                title="{{ t('settings.brand_slugs.cancel') }}">
          <i data-lucide="x" style="width:13px;height:13px"></i>
        </button>
        <button type="button" class="btn btn-ghost btn-sm brand-slug-delete-btn"
                onclick="openDeleteModal('brand-slug:{{ pair.brand }}', '{{ pair.brand }}')">
          <i data-lucide="trash-2" style="width:13px;height:13px"></i>
        </button>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% else %}
<div class="empty-state">
  <h2>{{ t('settings.brand_slugs.empty') }}</h2>
</div>
{% endif %}

{% endblock %}
```

Notes on the template:
- The slug column has BOTH a display span AND a hidden input. JS toggles which is visible during edit mode.
- The action column has pencil/check/cancel/trash. Pencil → edit mode (save+cancel visible, pencil hidden). Check → save and back to display mode. Cancel → revert + back to display mode.
- Delete reuses the existing `openDeleteModal()` from `base.html`. The "id" passed to the modal is `brand-slug:{brand}` — a string with a prefix, so the existing modal logic (which expects a numeric set id) needs a small tweak in Task 8 to handle this.

- [ ] **Step 2: Verify the existing Task 4 test still passes**

Run: `.venv/bin/pytest tests/test_settings_routes.py::test_settings_page_renders -v`
Expected: 1 passed. (The test asserts `"lego"` and `"pantasy"` are in the rendered HTML — both still present in the table.)

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 133 passed.

- [ ] **Step 3: Commit**

```
git add templates/settings_brand_slugs.html
git commit -m "$(cat <<'EOF'
feat(settings): full brand-slugs template (form, table, error banner)

Intro paragraph, add form at top, list table with per-row
edit/delete actions, conditional error callout, empty state.
JS for inline edit mode toggle and delete-modal integration
arrives in Task 8.
EOF
)"
```

---

### Task 8: Inline edit JS + delete-modal integration

**Files:**
- Modify: `templates/settings_brand_slugs.html` (add `{% block scripts %}`)
- Modify: `templates/base.html` (extend `openDeleteModal` / `delete-confirm-btn` to handle `brand-slug:…` ids)

- [ ] **Step 1: Extend `openDeleteModal` in `templates/base.html`**

Find the existing delete-modal JS in `templates/base.html` (around lines 60-78). The current `delete-confirm-btn` click handler assumes the id is numeric and POSTs to `/api/sets/${id}/delete`. We need to also support `brand-slug:{brand}` ids that POST to `/settings/brand-slugs/{brand}/delete`.

Replace the existing click handler:
```javascript
  document.getElementById('delete-confirm-btn').addEventListener('click', async () => {
    if (!_deleteId) return;
    await fetch(`/api/sets/${_deleteId}/delete`, { method: 'POST' });
    window.location.href = '/';
  });
```
With:
```javascript
  document.getElementById('delete-confirm-btn').addEventListener('click', async () => {
    if (!_deleteId) return;
    let url, redirect;
    if (typeof _deleteId === 'string' && _deleteId.startsWith('brand-slug:')) {
      const brand = _deleteId.slice('brand-slug:'.length);
      url = `/settings/brand-slugs/${encodeURIComponent(brand)}/delete`;
      redirect = '/settings/brand-slugs';
    } else {
      url = `/api/sets/${_deleteId}/delete`;
      redirect = '/';
    }
    await fetch(url, { method: 'POST' });
    window.location.href = redirect;
  });
```

The change preserves the existing set-deletion behaviour for numeric ids and adds the brand-slug branch when the id is a string starting with `brand-slug:`.

- [ ] **Step 2: Add inline edit JS to `templates/settings_brand_slugs.html`**

After the `{% endblock %}` for the content block (i.e., as the last thing in the file), add:

```html
{% block scripts %}
<script>
// ── Inline edit mode for brand-slug rows ───────────────────────────────────
document.querySelectorAll('.brand-slug-table tbody tr').forEach(row => {
  const display = row.querySelector('.brand-slug-table__slug-display');
  const input   = row.querySelector('.brand-slug-table__slug-input');
  const editBtn   = row.querySelector('.brand-slug-edit-btn');
  const saveBtn   = row.querySelector('.brand-slug-save-btn');
  const cancelBtn = row.querySelector('.brand-slug-cancel-btn');
  const deleteBtn = row.querySelector('.brand-slug-delete-btn');
  if (!display || !input || !editBtn) return;

  const brand = row.dataset.brand;

  function enterEditMode() {
    display.classList.add('hidden');
    input.classList.remove('hidden');
    editBtn.classList.add('hidden');
    deleteBtn.classList.add('hidden');
    saveBtn.classList.remove('hidden');
    cancelBtn.classList.remove('hidden');
    input.focus();
    input.select();
  }

  function leaveEditMode() {
    display.classList.remove('hidden');
    input.classList.add('hidden');
    editBtn.classList.remove('hidden');
    deleteBtn.classList.remove('hidden');
    saveBtn.classList.add('hidden');
    cancelBtn.classList.add('hidden');
  }

  editBtn.addEventListener('click', enterEditMode);
  cancelBtn.addEventListener('click', () => {
    input.value = input.dataset.original;
    leaveEditMode();
  });

  saveBtn.addEventListener('click', async () => {
    const newSlug = input.value.trim();
    if (!newSlug) {
      // Server would redirect with ?error=empty, but for the inline path
      // we just give the input focus again.
      input.focus();
      return;
    }
    saveBtn.disabled = true;
    const body = new FormData();
    body.append('slug', newSlug);
    const r = await fetch(`/settings/brand-slugs/${encodeURIComponent(brand)}/update`,
                          { method: 'POST', body });
    saveBtn.disabled = false;
    if (r.ok) {
      // The redirect was followed by fetch; we now update the DOM in place
      // to reflect the new value, then leave edit mode.
      display.textContent = newSlug;
      input.dataset.original = newSlug;
      leaveEditMode();
    } else {
      alert('Update failed: ' + r.status);
    }
  });

  // Enter = save, Esc = cancel
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter')      { e.preventDefault(); saveBtn.click(); }
    else if (e.key === 'Escape'){ e.preventDefault(); cancelBtn.click(); }
  });
});
</script>
{% endblock %}
```

- [ ] **Step 3: Verify tests still green**

Run: `.venv/bin/pytest -v`
Expected: 133 passed.

- [ ] **Step 4: Smoke test in browser**

Start uvicorn on port 8129 in the background:
```
.venv/bin/uvicorn main:app --port 8129
```
Run with `run_in_background: true`. Wait for startup.

Visit `http://localhost:8129/settings/brand-slugs`. Verify:
- Click pencil on a row → input + save/cancel appear, focus moves into input
- Edit the slug, press Enter → row updates inline; new value visible after save
- Cancel button restores original
- Delete button opens the modal with the brand name; confirm → row disappears after reload
- Add form at top creates a new row (page reloads); duplicate triggers error banner

Kill: `pkill -f "port 8129"`.

- [ ] **Step 5: Commit**

```
git add templates/base.html templates/settings_brand_slugs.html
git commit -m "$(cat <<'EOF'
feat(settings): inline edit + delete-modal integration for brand-slugs

Pencil → enter edit mode (slug becomes input, save/cancel buttons
appear). Save POSTs to the update endpoint and swaps display back
in place. Cancel reverts. Enter/Esc keyboard shortcuts. Delete
modal extended to recognise "brand-slug:{brand}" ids alongside
the existing numeric set ids.
EOF
)"
```

---

### Task 9: Gear icon in site header

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add the gear icon to the header**

Find the existing `<div class="site-header__actions">` block in `templates/base.html` (around lines 18-28). The current shape:

```html
      <div class="site-header__actions">
        <form action="/set-lang" method="post" style="display:inline">
          ...
          <button type="submit" class="lang-toggle">{{ 'EN' if lang == 'de' else 'DE' }}</button>
        </form>
      </div>
```

Insert a gear-icon link BEFORE the lang-toggle form:

```html
      <div class="site-header__actions">
        <a href="/settings/brand-slugs" class="settings-link" title="{{ t('nav.settings') }}">
          <i data-lucide="settings" style="width:16px;height:16px"></i>
        </a>
        <form action="/set-lang" method="post" style="display:inline">
          ...
          <button type="submit" class="lang-toggle">{{ 'EN' if lang == 'de' else 'DE' }}</button>
        </form>
      </div>
```

The `.settings-link` CSS class is added in Task 10. Until then the icon will render with default link styling — visible but unstyled.

- [ ] **Step 2: Verify the icon shows on every page**

Smoke check via TestClient — every existing page extends base.html, so the icon should now appear on `/`, `/add`, `/sets/{id}`, `/sets/{id}/edit`, `/import/brickset`, `/settings/brand-slugs`:

```
cd /Users/hhalfpap/git/projects/own/brickset-tracker && .venv/bin/python -c "
from fastapi.testclient import TestClient
from main import app
from execution import db as dbmod
from execution.db import init_db
from tests.factories import make_set
import tempfile, pathlib
with tempfile.TemporaryDirectory() as tmp:
    dbmod.DB_PATH = pathlib.Path(tmp) / 'test.db'
    init_db()
    sid = make_set(brand='LEGO', set_number='1', name='X', part_count=1)
    client = TestClient(app)
    for path in ['/', '/add', f'/sets/{sid}', f'/sets/{sid}/edit', '/import/brickset', '/settings/brand-slugs']:
        r = client.get(path)
        ok = '/settings/brand-slugs' in r.text and 'data-lucide=\"settings\"' in r.text
        print(f'{path}: {r.status_code} settings-link={\"yes\" if ok else \"NO\"}')
"
```

Expected: every path 200 with `settings-link=yes`.

Run the full pytest suite to confirm no regression:
Run: `.venv/bin/pytest -v`
Expected: 133 passed.

- [ ] **Step 3: Commit**

```
git add templates/base.html
git commit -m "$(cat <<'EOF'
feat(ui): gear icon in site header links to settings/brand-slugs

Visible on every page (the header is in base.html). Placed just
left of the language toggle, matching the spec's "leave room for
future settings sections" intent. Styling lands in Task 10.
EOF
)"
```

---

### Task 10: CSS for settings page + cache buster bump

**Files:**
- Modify: `static/style.css` (append new rules)
- Modify: `templates/base.html` (bump `?v=6` → `?v=7`)

- [ ] **Step 1: Bump cache buster**

In `templates/base.html`, find `<link rel="stylesheet" href="/static/style.css?v=6">` and change to `?v=7`.

- [ ] **Step 2: Append CSS to `static/style.css`**

Append at the end:

```css
/* ---------- Settings (general) ------------------------------------- */
.settings-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: rgba(245, 240, 232, 0.75);
  background: rgba(245, 240, 232, 0.12);
  border: 1px solid rgba(245, 240, 232, 0.25);
  border-radius: var(--r-sm);
  text-decoration: none;
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
  margin-right: var(--sp-2);
}
.settings-link:hover {
  background: rgba(245, 240, 232, 0.22);
  color: var(--kartenpapier);
}

.settings-intro {
  font: 400 13px/1.5 var(--font-body);
  color: var(--fg-muted);
  margin-bottom: var(--sp-4);
  max-width: 720px;
}

.settings-section {
  margin-bottom: var(--sp-5);
}
.settings-section__heading {
  font: 500 12px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--sp-3);
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--rule);
}

/* ---------- Brand-Slug Settings ------------------------------------ */
.brand-slug-add-form {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-end;
  flex-wrap: wrap;
}
.brand-slug-add-form .field { min-width: 200px; }
.brand-slug-add-form .field label {
  font: 500 10px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--sp-1);
  display: block;
}
.brand-slug-add-form .field input {
  width: 100%;
  font: 400 14px/1 var(--font-body);
  padding: 8px 12px;
  border: 1px solid rgba(27, 58, 92, 0.28);
  border-radius: var(--r-md);
  background: var(--weiss);
}

.brand-slug-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.brand-slug-table thead th {
  font: 500 10px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  text-align: left;
  padding: var(--sp-3) var(--sp-3);
  border-bottom: 1px solid var(--rule);
}
.brand-slug-table tbody td {
  padding: var(--sp-3) var(--sp-3);
  border-bottom: 1px solid var(--rule);
  vertical-align: middle;
}
.brand-slug-table__brand {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--fg);
}
.brand-slug-table__slug {
  font-family: var(--font-mono);
  font-size: 13px;
}
.brand-slug-table__slug-input {
  font: 400 13px/1 var(--font-mono);
  padding: 6px 10px;
  border: 1px solid rgba(27, 58, 92, 0.28);
  border-radius: var(--r-md);
  background: var(--weiss);
  width: 200px;
}
.brand-slug-table__actions {
  text-align: right;
  white-space: nowrap;
}
.brand-slug-table__actions .btn { padding: 6px 10px; }
```

- [ ] **Step 3: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 133 passed.

- [ ] **Step 4: Smoke check cache buster**

```
cd /Users/hhalfpap/git/projects/own/brickset-tracker && .venv/bin/python -c "
from fastapi.testclient import TestClient
from main import app
r = TestClient(app).get('/')
assert 'style.css?v=7' in r.text, 'cache buster not bumped'
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```
git add static/style.css templates/base.html
git commit -m "$(cat <<'EOF'
style: add settings page CSS + bump cache buster

Gear icon styled to match the existing lang-toggle aesthetic.
Settings page: intro paragraph, two-column add form, full-width
brand-slug table with mono-styled values, inline edit input.
v=6 → v=7.
EOF
)"
```

---

### Task 11: Final E2E manual verification

**Files:** none modified.

Walk through these scenarios in the live server in both DE and EN.

- [ ] **Step 1: Restart the dev server**

```
pkill -f "uvicorn main:app --port 8123" 2>/dev/null
.venv/bin/uvicorn main:app --port 8123 --reload
```
Run with `run_in_background: true`. Wait for `Application startup complete.`.

- [ ] **Step 2: Production DB migration**

Confirm the user's existing DB picked up the new table cleanly:

```
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/brickset.db')
conn.row_factory = sqlite3.Row
cols = {r['name'] for r in conn.execute('PRAGMA table_info(brand_slugs)').fetchall()}
assert cols == {'brand', 'slug', 'created_at', 'updated_at'}, cols
n = conn.execute('SELECT COUNT(*) AS n FROM brand_slugs').fetchone()['n']
print(f'brand_slugs table: {n} rows (expect ≥9 from seed)')
"
```
Expected: 9 or more rows.

- [ ] **Step 3: Gear icon on every page**

Visit `http://localhost:8123/`. The gear icon should be visible at top-right (next to the language toggle). Click it → navigates to `/settings/brand-slugs`.

Visit a few other pages (`/add`, `/sets/{some-id}`, `/sets/{some-id}/edit`, `/import/brickset`). Gear icon is visible on each.

- [ ] **Step 4: Settings page**

On `/settings/brand-slugs`:
- Intro paragraph visible
- Add form at top (Brand + Slug inputs + Add button)
- Table below with seeded entries sorted alphabetically (blue brixx, bluebrixx, cada, cobi, funwhole, lego, lumibricks, mould king, pantasy)
- Per-row pencil and trash buttons

- [ ] **Step 5: Add a new slug**

In the Add form, enter `Foo Brand` / `foo`. Submit → page reloads, new row appears in the table.

Try adding `lego` / `xyz` → error banner appears ("Brand 'lego' already has a slug").

Try submitting with empty inputs → browser blocks (HTML `required`), or if you bypass it, server redirects with `?error=empty`.

- [ ] **Step 6: Edit a slug inline**

Click pencil on the `Foo Brand` row. Slug column becomes an input, focused. Type `foo-new`, press Enter. Row updates in place; pencil/trash reappear; the new value persists across page reload.

Click pencil, type something, press Esc → original value restored.

- [ ] **Step 7: Delete a slug**

Click trash on the `Foo Brand` row → confirmation modal appears with the brand name. Cancel → modal closes, row stays. Confirm → row disappears; reload shows it's gone.

Try deleting ALL rows → empty-state message appears: "No brand slugs configured yet. Add the first one above." Reseed by re-adding any row (or just restart the server, which re-seeds via init_db).

- [ ] **Step 8: Auto-populate from successful lookup**

Find a brand NOT currently in the slug table (e.g. add a deliberate one — but careful about quota). Or just verify with the existing seed data that the lookup flow works and the seeded entries remain.

If you want to test fresh: delete the seeded `lego` entry, then `/add` a LEGO set. After lookup succeeds, visit `/settings/brand-slugs` — `lego` should be back (auto-populated from the successful scrape).

- [ ] **Step 9: Language toggle**

Switch DE ↔ EN at any point. Settings page title, intro, column headers, error messages, button labels all translate.

- [ ] **Step 10: Existing functionality not affected**

Visit `/` — collection list renders normally. Click an existing set → details renders. Click pencil → edit renders. `/add` works. Brickset import works.

- [ ] **Step 11: Mark verification commit**

```
git commit --allow-empty -m "$(cat <<'EOF'
chore: verify brand-slugs settings end-to-end

All scenarios in plan Task 11 pass in both DE and EN. Production
DB picked up the new brand_slugs table cleanly (seeded from
existing dict). Gear icon visible on every page. Add / inline edit
/ delete all working. Auto-populate confirmed via fresh lookup.
EOF
)"
```

---

## Done

Iteration 4.5 complete. Brand-slug mappings are now user-configurable through the `/settings/brand-slugs` page, accessible via a gear icon in the site header. Successful merlinssteine.de scrapes auto-populate the table; users edit/delete via inline controls; the existing hardcoded dict stays as seed data for fresh installs.

Next on the V1 path: **Code review → Phase T (LaunchAgent deployment) → V1 done**.
