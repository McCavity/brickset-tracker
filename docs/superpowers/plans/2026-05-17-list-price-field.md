# List Price Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `list_price` column to the `sets` table — separate retail price (auto-filled from merlinssteine.de / Brickset on lookup) from `price_paid` (what the user actually paid).

**Architecture:** Additive schema change (idempotent `ALTER TABLE` in `init_db`). Scraper's existing Listenpreis extraction is re-keyed from `price` to `list_price`. Brickset enrichment newly extracts `LEGOCom.DE.retailPrice`. Lookup router maps both into `prefill["list_price"]` and stops touching `price_paid` (per design: system cannot know what the user paid). Forms get a new `list_price` input above `price_paid` with a small `← copy` button. List view shows `list_price` parenthetically only when it differs from `price_paid`.

**Tech Stack:** FastAPI 0.115, Starlette 0.46, Jinja2 3.1, SQLite (stdlib `sqlite3`), pytest with monkeypatch for HTTP mocking.

**Spec:** `docs/superpowers/specs/2026-05-17-list-price-field-design.md`

---

## Phase 0 — Schema + scraper rename

### Task 1: Schema migration in `init_db()`

**Files:**
- Modify: `execution/db.py` (extend `init_db()` with additive ALTER TABLE; also add column to canonical CREATE TABLE for fresh installs)
- Create: `tests/test_list_price_schema.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_list_price_schema.py`:
```python
"""The sets table has a list_price column after init_db runs."""
from execution.db import get_connection


def _columns(conn) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(sets)").fetchall()}


def test_list_price_column_exists(db):
    """db fixture calls init_db on a fresh temp DB."""
    with get_connection() as conn:
        cols = _columns(conn)
    assert "list_price" in cols


def test_list_price_column_is_nullable(db):
    """Existing rows without list_price stay NULL. Verify by inserting
    without the column and reading it back."""
    from tests.factories import make_set
    set_id = make_set(brand="LEGO", set_number="42171", name="X", part_count=100)
    with get_connection() as conn:
        row = conn.execute("SELECT list_price FROM sets WHERE id=?", (set_id,)).fetchone()
    assert row["list_price"] is None


def test_alter_table_is_idempotent(db):
    """Running init_db twice on the same DB must not error."""
    from execution.db import init_db
    init_db()  # second call
    init_db()  # third call for good measure
    # If no exception, the migration is properly idempotent.
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_list_price_schema.py -v`
Expected: `test_list_price_column_exists` and `test_list_price_column_is_nullable` fail (column missing). `test_alter_table_is_idempotent` may pass trivially since init_db doesn't error today.

- [ ] **Step 3: Update `init_db()` in `execution/db.py`**

The existing `init_db()` does `conn.executescript(...)` to CREATE TABLE IF NOT EXISTS. Two changes:

1. Add `list_price REAL` to the CREATE TABLE column list (between `price_paid REAL,` and `brickset_set_id INTEGER,`).
2. After the `executescript(...)` call, run an idempotent ALTER TABLE for existing databases.

Replace the existing `init_db` function with:

```python
def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sets (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ean              TEXT,
                brand            TEXT    NOT NULL,
                set_number       TEXT    NOT NULL,
                name             TEXT    NOT NULL,
                part_count       INTEGER NOT NULL,
                condition        TEXT,
                location         TEXT,
                date_of_purchase TEXT,
                note             TEXT,
                theme            TEXT,
                release_year     INTEGER,
                web_images       TEXT,
                own_photos       TEXT,
                minifigs         INTEGER,
                price_paid       REAL,
                list_price       REAL,
                brickset_set_id  INTEGER,
                status           TEXT    NOT NULL DEFAULT 'draft',
                created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ean_cache (
                ean          TEXT PRIMARY KEY,
                brand        TEXT NOT NULL,
                set_number   TEXT NOT NULL,
                source       TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS scrape_quota (
                service      TEXT NOT NULL,
                date         TEXT NOT NULL,
                count        INTEGER DEFAULT 0,
                PRIMARY KEY (service, date)
            );

            CREATE INDEX IF NOT EXISTS idx_sets_brand  ON sets(brand);
            CREATE INDEX IF NOT EXISTS idx_sets_date   ON sets(date_of_purchase);
            CREATE INDEX IF NOT EXISTS idx_sets_status ON sets(status);
        """)

        # Idempotent migration for databases created before list_price existed.
        # SQLite raises OperationalError if the column is already present;
        # CREATE TABLE IF NOT EXISTS above won't add columns to an existing table.
        try:
            conn.execute("ALTER TABLE sets ADD COLUMN list_price REAL")
        except sqlite3.OperationalError:
            pass
```

The CREATE TABLE handles fresh databases (the canonical schema includes `list_price`); the ALTER TABLE handles pre-existing databases (the user's production DB) by adding the column on next startup. The two together cover both paths.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_list_price_schema.py -v`
Expected: 3 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 82 passed (79 prior + 3 new).

- [ ] **Step 5: Commit**

```
git add execution/db.py tests/test_list_price_schema.py
git commit -m "$(cat <<'EOF'
feat(db): add list_price column to sets table

Fresh DBs get the column via the canonical CREATE TABLE; existing
DBs (incl. the user's production DB) get it via an idempotent
ALTER TABLE that swallows the "duplicate column" OperationalError
on subsequent app starts. No data loss; existing rows initialise
to NULL.
EOF
)"
```

---

### Task 2: Scraper rename `price` → `list_price`

**Files:**
- Modify: `execution/scraper.py` (rename the result dict key)
- Create: `tests/test_scraper_list_price.py`

- [ ] **Step 1: Write the failing test**

The scraper's `scrape_set()` is the public entry. We don't want to hit the live merlinssteine.de in tests (rate limit), but we DO want to verify the field name in the dict it returns. The cleanest test is at the level of `_parse_price` + a minimal end-to-end with monkeypatched HTML.

Write `tests/test_scraper_list_price.py`:
```python
"""Scraper result dict uses 'list_price' (not 'price') for the
extracted Listenpreis. Verified by monkeypatching the HTTP layer
and feeding canned HTML."""
import httpx
import pytest

from execution import scraper


class _FakeResponse:
    def __init__(self, html: str, status: int = 200):
        self.text = html
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _FakeClient:
    """Single-response fake httpx.AsyncClient."""
    _html: str = ""

    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def get(self, url, headers=None, follow_redirects=True):
        return _FakeResponse(_FakeClient._html)


_MINIMAL_HTML = """
<html><body>
<h1>LEGO 42171 — McLaren P1</h1>
<ul>
  <li>Marke: LEGO</li>
  <li>Setnummer: 42171</li>
  <li>Teile: 3893</li>
  <li>Thema: Technic</li>
  <li>Listenpreis: 449,99 EUR</li>
  <li>Erscheinungsjahr: 2023</li>
</ul>
</body></html>
"""


@pytest.fixture
def fake_scrape(monkeypatch, db):
    _FakeClient._html = _MINIMAL_HTML
    monkeypatch.setattr(scraper.httpx, "AsyncClient", _FakeClient)
    # Disable rate-limit check so the test is reproducible
    monkeypatch.setattr(scraper, "check_quota", lambda svc: True)
    monkeypatch.setattr(scraper, "increment_quota", lambda svc: None)


async def test_scrape_result_uses_list_price_key(fake_scrape):
    result = await scraper.scrape_set("lego", "42171")
    assert result["status"] == "success"
    assert "list_price" in result
    assert result["list_price"] == 449.99
    assert "price" not in result, "Old key 'price' should no longer be in the result"
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_scraper_list_price.py -v`
Expected: `test_scrape_result_uses_list_price_key` fails because the scraper still keys this as `"price"`, not `"list_price"`.

If the test fails for a different reason (e.g. the fake HTML doesn't parse), inspect `execution/scraper.py:scrape_set` for what fields it actually requires. The current scraper looks for `Listenpreis:` in `<li>` text — the fixture HTML provides that. Adjust the fixture if needed to satisfy other required-field extractions.

- [ ] **Step 3: Rename in `execution/scraper.py`**

Find this block in `execution/scraper.py` (around line 114):
```python
    # --- Price (Listenpreis) ---
    price = None
    ...
            if text.startswith("Listenpreis:"):
                ...
                    price = _parse_price(m.group(1))
```

And later (around line 137):
```python
        "price":        price,
```

Apply these renames:
1. Local variable `price` → `list_price` throughout the function.
2. Result dict key `"price":` → `"list_price":`.
3. Comment `# --- Price (Listenpreis) ---` → `# --- List price (Listenpreis) ---`.

Do NOT rename `_parse_price` (the helper) — its name is fine and it's used elsewhere.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_scraper_list_price.py -v`
Expected: 1 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 83 passed (82 prior + 1 new). If any other test fails because it expected the old `"price"` key, that's a real regression — fix it as part of this commit (it shouldn't happen because no existing test references that key — but verify).

- [ ] **Step 5: Commit**

```
git add execution/scraper.py tests/test_scraper_list_price.py
git commit -m "$(cat <<'EOF'
feat(scraper): rename result key 'price' to 'list_price'

The scraper already extracts merlinssteine.de's Listenpreis; this
just stops calling it 'price' so downstream code can route it to
the new list_price field instead of price_paid.
EOF
)"
```

---

## Phase 1 — Brickset enrichment

### Task 3: `_map_set` extracts `list_price` from `LEGOCom.DE.retailPrice`

**Files:**
- Modify: `execution/brickset.py:_map_set()` (extend the returned dict)
- Modify: `tests/test_map_owned_set.py` (extend an existing test fixture; `_map_owned_set` delegates to `_map_set` so testing the union is enough)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_map_owned_set.py`:
```python
def test_extracts_list_price_from_legocom_de():
    """Brickset nests retail prices under LEGOCom.<country>.retailPrice.
    For the German user, the EUR figure is LEGOCom.DE.retailPrice."""
    raw = {
        "setID": 23456, "number": "10298", "name": "Vespa 125",
        "pieces": 1106, "theme": "Creator Expert", "year": 2022,
        "barcode": {}, "image": {},
        "LEGOCom": {
            "US": {"retailPrice": 99.99},
            "UK": {"retailPrice": 89.99},
            "DE": {"retailPrice": 99.99, "dateFirstAvailable": "2022-03-02T00:00:00Z"},
        },
        "collection": {"qtyOwned": 1},
    }
    r = _map_owned_set(raw)
    assert r["list_price"] == 99.99


def test_list_price_is_none_when_legocom_missing():
    raw = {"setID": 1, "number": "10298", "name": "X", "pieces": 1}
    assert _map_owned_set(raw)["list_price"] is None


def test_list_price_is_none_when_de_branch_missing():
    raw = {
        "setID": 1, "number": "10298", "name": "X", "pieces": 1,
        "LEGOCom": {"US": {"retailPrice": 99.99}},  # only US, no DE
    }
    assert _map_owned_set(raw)["list_price"] is None


def test_list_price_is_none_when_retail_price_missing():
    raw = {
        "setID": 1, "number": "10298", "name": "X", "pieces": 1,
        "LEGOCom": {"DE": {"dateFirstAvailable": "2022-03-02T00:00:00Z"}},
    }
    assert _map_owned_set(raw)["list_price"] is None
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_map_owned_set.py -v`
Expected: 4 new tests fail (list_price is not in the mapped dict).

- [ ] **Step 3: Extend `_map_set` in `execution/brickset.py`**

Find `_map_set(s: dict) -> dict:` (around line 105). Inside the function, add the LEGOCom.DE.retailPrice extraction. Replace the function with:

```python
def _map_set(s: dict) -> dict:
    barcode = s.get("barcode") or {}
    img     = s.get("image") or {}
    lego_de = (s.get("LEGOCom") or {}).get("DE") or {}
    return {
        "set_id":     s.get("setID"),
        "name":       s.get("name"),
        "pieces":     s.get("pieces"),
        "theme":      s.get("theme"),
        "year":       s.get("year"),
        "ean":        barcode.get("EAN"),
        "image_url":  img.get("imageURL"),
        "list_price": lego_de.get("retailPrice"),
    }
```

The chained `.get(...) or {}` calls guard against missing `LEGOCom`, missing `DE`, or `None` values at any level; if anything along the path is missing or null, `list_price` ends up `None`.

`_map_owned_set` already delegates to `_map_set` for the base mapping, so it picks up `list_price` automatically.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_map_owned_set.py -v`
Expected: all tests pass (7 total: 3 pre-existing + 4 new).

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 87 passed (83 prior + 4 new).

- [ ] **Step 5: Commit**

```
git add execution/brickset.py tests/test_map_owned_set.py
git commit -m "$(cat <<'EOF'
feat(brickset): extract list_price from LEGOCom.DE.retailPrice

Brickset nests retail prices under LEGOCom.<country>.retailPrice.
For the EU user we use the DE branch (EUR). Defensive .get() chain
returns None when LEGOCom, DE, or retailPrice is missing — common
for old, regional, or unreleased sets.
EOF
)"
```

---

## Phase 2 — Router rewiring

### Task 4: `lookup_router` maps `list_price` (not `price_paid`)

**Files:**
- Modify: `navigation/lookup_router.py` (both merge helpers)
- Create: `tests/test_lookup_router_list_price.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_lookup_router_list_price.py`:
```python
"""After Task 2's scraper rename, the lookup router must route the
extracted list_price into prefill['list_price'] and must NOT touch
prefill['price_paid']. Brickset's list_price fills gaps."""
import pytest

from navigation import lookup_router


# Test 1: merlinssteine result → prefill["list_price"]; price_paid untouched

def test_merge_from_merlinssteine_writes_list_price():
    prefill = {"brand": "LEGO", "set_number": "42171"}
    result = {
        "status": "success",
        "name": "McLaren P1",
        "part_count": 3893,
        "theme": "Technic",
        "release_year": 2023,
        "list_price": 449.99,
        "ean": "5702017595672",
    }
    lookup_router._merge_from_merlinssteine(prefill, result)
    assert prefill["list_price"] == 449.99
    assert "price_paid" not in prefill, "price_paid must remain unset (per design A)"


def test_merge_from_merlinssteine_handles_missing_list_price():
    """If merlinssteine didn't extract a list price, prefill stays free of the key."""
    prefill = {"brand": "BlueBrixx", "set_number": "10000"}
    result = {"status": "success", "name": "Castle", "part_count": 500}
    lookup_router._merge_from_merlinssteine(prefill, result)
    assert "list_price" not in prefill
    assert "price_paid" not in prefill


# Test 2: Brickset gap-fills list_price; doesn't overwrite an existing one

def test_merge_from_brickset_fills_list_price_when_missing():
    prefill = {"brand": "LEGO", "set_number": "10298"}
    bs = {
        "set_id":     23456,
        "name":       "Vespa 125",
        "pieces":     1106,
        "theme":      "Creator Expert",
        "year":       2022,
        "list_price": 99.99,
    }
    lookup_router._merge_from_brickset(prefill, bs)
    assert prefill["list_price"] == 99.99
    assert "price_paid" not in prefill


def test_merge_from_brickset_does_not_overwrite_existing_list_price():
    """merlinssteine wins where it has data; Brickset only fills gaps."""
    prefill = {"brand": "LEGO", "set_number": "10298", "list_price": 89.99}
    bs = {"set_id": 1, "name": "X", "list_price": 99.99}
    lookup_router._merge_from_brickset(prefill, bs)
    assert prefill["list_price"] == 89.99  # merlinssteine's value won


def test_merge_from_brickset_handles_missing_list_price():
    prefill = {"brand": "LEGO", "set_number": "10298"}
    bs = {"set_id": 1, "name": "X"}  # no list_price key
    lookup_router._merge_from_brickset(prefill, bs)
    assert "list_price" not in prefill
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_lookup_router_list_price.py -v`
Expected: at least `test_merge_from_merlinssteine_writes_list_price` and the Brickset tests fail (the current code still maps to `price_paid` and doesn't touch `list_price` at all).

- [ ] **Step 3: Update both merge helpers in `navigation/lookup_router.py`**

Open `navigation/lookup_router.py`. Find `_merge_from_merlinssteine` (around line 122). Replace it with:

```python
def _merge_from_merlinssteine(prefill: dict, result: dict) -> None:
    """Copy merlinssteine fields into prefill, only when they have truthy values.

    The extracted Listenpreis flows to `list_price` (not `price_paid`); the
    system can't know what the user actually paid, so `price_paid` stays
    blank for the user to fill in.
    """
    field_map = (
        ("name",         result.get("name")),
        ("part_count",   result.get("part_count")),
        ("theme",        result.get("theme")),
        ("release_year", result.get("release_year")),
        ("list_price",   result.get("list_price")),
    )
    for key, value in field_map:
        if value:
            prefill[key] = value

    if result.get("ean"):
        prefill["ean"] = result["ean"]
    if result.get("image_url"):
        prefill["web_images"] = [result["image_url"]]
    if result.get("brand_full"):
        prefill["brand"] = result["brand_full"]
```

Note the two changes vs. the existing code:
1. The `("price_paid", result.get("price"))` tuple is replaced by `("list_price", result.get("list_price"))`.
2. The docstring documents WHY price_paid stays blank.

Find `_merge_from_brickset` (around line 143). Replace it with:

```python
def _merge_from_brickset(prefill: dict, bs: dict) -> None:
    """Copy Brickset fields into prefill, filling only the gaps merlinssteine left.

    `brickset_set_id` is always set (Brickset is the authoritative source).
    `list_price` is gap-filled — merlinssteine's Listenpreis wins when present.
    """
    field_map = (
        ("name",         bs.get("name")),
        ("part_count",   bs.get("pieces")),
        ("theme",        bs.get("theme")),
        ("release_year", bs.get("year")),
        ("list_price",   bs.get("list_price")),
    )
    for key, value in field_map:
        if value and not prefill.get(key):
            prefill[key] = value

    if bs.get("ean") and not prefill.get("ean"):
        prefill["ean"] = bs["ean"]
    if not prefill.get("web_images") and bs.get("image_url"):
        prefill["web_images"] = [bs["image_url"]]

    prefill["brickset_set_id"] = bs.get("set_id")
```

The only change here is the new `("list_price", bs.get("list_price"))` tuple in `field_map`.

- [ ] **Step 4: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_lookup_router_list_price.py -v`
Expected: 5 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 92 passed (87 prior + 5 new).

- [ ] **Step 5: Commit**

```
git add navigation/lookup_router.py tests/test_lookup_router_list_price.py
git commit -m "$(cat <<'EOF'
feat(lookup): route list_price (not price_paid) from both sources

merlinssteine's Listenpreis and Brickset's LEGOCom.DE.retailPrice
now both flow into prefill['list_price']. price_paid is no longer
auto-filled — the system can't know what the user paid; only the
user can enter that. merlinssteine wins where it has data; Brickset
fills gaps for LEGO sets where merlinssteine didn't have the set.
EOF
)"
```

---

## Phase 3 — set_manager column plumbing

### Task 5: `save_set`, `update_set`, `get_sets` handle `list_price`

**Files:**
- Modify: `navigation/set_manager.py`
- Create: `tests/test_set_manager_list_price.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_set_manager_list_price.py`:
```python
"""save_set / update_set / get_sets / get_set round-trip list_price."""
from navigation.set_manager import save_set, update_set, get_set, get_sets


def test_save_set_persists_list_price(db):
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": 99.99,
    })
    set_id = result["id"]
    row = get_set(set_id)
    assert row["list_price"] == 99.99


def test_save_set_accepts_german_decimal_in_list_price(db):
    """Same German-or-dot parsing as price_paid (via the _float helper)."""
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": "99,99",
    })
    set_id = result["id"]
    row = get_set(set_id)
    assert row["list_price"] == 99.99


def test_save_set_with_no_list_price_stores_null(db):
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106,
    })
    set_id = result["id"]
    row = get_set(set_id)
    assert row["list_price"] is None


def test_update_set_persists_list_price(db):
    from tests.factories import make_set
    set_id = make_set(brand="LEGO", set_number="10298", name="V", part_count=1)
    update_set(set_id, {
        "brand": "LEGO", "set_number": "10298", "name": "V",
        "part_count": 1106, "list_price": 199.99,
        "existing_own_photos": "[]",
    })
    row = get_set(set_id)
    assert row["list_price"] == 199.99


def test_update_set_can_clear_list_price(db):
    """Saving an empty list_price clears the column to NULL."""
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": 99.99,
    })
    set_id = result["id"]
    update_set(set_id, {
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": "",
        "existing_own_photos": "[]",
    })
    row = get_set(set_id)
    assert row["list_price"] is None


def test_get_sets_returns_list_price(db):
    """list_price is in the SELECT column list, so it flows through
    to the list-view rendering layer."""
    save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": 99.99,
    })
    rows = get_sets()
    assert len(rows) == 1
    assert rows[0]["list_price"] == 99.99
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_set_manager_list_price.py -v`
Expected: most/all tests fail. `save_set` and `update_set` don't yet pass `list_price` in their INSERT/UPDATE column lists, and `get_sets` doesn't include `list_price` in its SELECT (so even if the DB row has the value, the returned dict won't).

- [ ] **Step 3: Update `save_set` in `navigation/set_manager.py`**

Find the INSERT statement (around line 38). The current column list is:
```
(ean, brand, set_number, name, part_count, condition, location,
 date_of_purchase, note, theme, release_year, web_images, own_photos,
 minifigs, price_paid, brickset_set_id, status)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
```
That's 17 columns / 17 placeholders. Add `list_price` between `price_paid` and `brickset_set_id`, plus one more `?`:

```python
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
```

- [ ] **Step 4: Update `update_set` in `navigation/set_manager.py`**

Find the UPDATE statement (around line 224). Add `list_price=?` after `price_paid=?`:

```python
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
```

- [ ] **Step 5: Update `get_sets` SELECT in `navigation/set_manager.py`**

Find the SELECT in `get_sets` (around line 105). Add `list_price` after `price_paid`:

```python
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
```

`get_set()` uses `SELECT *` so it already picks up the new column for free. `_row_to_dict` is permissive (just `dict(row)`), so the new column flows through.

- [ ] **Step 6: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_set_manager_list_price.py -v`
Expected: 6 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 98 passed (92 prior + 6 new).

- [ ] **Step 7: Commit**

```
git add navigation/set_manager.py tests/test_set_manager_list_price.py
git commit -m "$(cat <<'EOF'
feat(sets): plumb list_price through save_set / update_set / get_sets

INSERT and UPDATE column lists gain list_price; the get_sets SELECT
gains it too. get_set's SELECT * picks it up automatically. The
existing _float helper handles German-or-dot decimal parsing for
the new field, identical to price_paid.
EOF
)"
```

---

## Phase 4 — UI (manual verification)

### Task 6: New `list_price` field + copy button in `templates/add.html`

**Files:**
- Modify: `templates/add.html`

- [ ] **Step 1: Add the new field above `price_paid`**

In `templates/add.html`, find the `price_paid` field (around line 105):
```html
    <div class="field">
      <label for="f-price">{{ t('add.price_paid') }}</label>
      <input type="text" inputmode="decimal" id="f-price" name="price_paid"
             value="{{ prefill.price_paid or '' }}" style="font-family:var(--font-mono)">
    </div>
```

Replace it with the two-field block:
```html
    <div class="field">
      <label for="f-list-price">{{ t('add.list_price') }}</label>
      <input type="text" inputmode="decimal" id="f-list-price" name="list_price"
             value="{{ prefill.list_price or '' }}" style="font-family:var(--font-mono)">
    </div>

    <div class="field">
      <label for="f-price">{{ t('add.price_paid') }}</label>
      <div style="display:flex;gap:var(--sp-2);align-items:center">
        <input type="text" inputmode="decimal" id="f-price" name="price_paid"
               value="{{ prefill.price_paid or '' }}" style="font-family:var(--font-mono);flex:1">
        <button type="button" class="btn btn-ghost btn-sm" id="copy-list-to-price"
                onclick="document.getElementById('f-price').value = document.getElementById('f-list-price').value"
                title="{{ t('add.copy_from_list_price') }}">←</button>
      </div>
    </div>
```

Notes on the markup:
- The list_price field uses the same input style + classes as price_paid.
- The copy button is positioned inside the price_paid field's container (right of the input). Clicking it copies whatever's currently in `#f-list-price` into `#f-price`. Pure inline JS — no event listener registration needed.
- The flex container keeps the input expanding while the button stays compact.

- [ ] **Step 2: Update the `applyPrefill` map (JS block lower in the file)**

Find the `applyPrefill` function in the `{% block scripts %}` (around line 263). The current map looks like:
```javascript
  const map = {
    brand: 'f-brand', set_number: 'f-setnumber', name: 'f-name',
    part_count: 'f-parts', theme: 'f-theme', release_year: 'f-year',
    price_paid: 'f-price', ean: 'f-ean', note: 'f-note',
    condition: 'f-condition', location: 'f-location', date_of_purchase: 'f-date',
  };
```
Add `list_price: 'f-list-price'`:
```javascript
  const map = {
    brand: 'f-brand', set_number: 'f-setnumber', name: 'f-name',
    part_count: 'f-parts', theme: 'f-theme', release_year: 'f-year',
    price_paid: 'f-price', list_price: 'f-list-price', ean: 'f-ean', note: 'f-note',
    condition: 'f-condition', location: 'f-location', date_of_purchase: 'f-date',
  };
```

- [ ] **Step 3: Update the language-switch state-persistence array**

Find `_FIELD_IDS` (around line 347):
```javascript
const _FIELD_IDS = ['f-brand','f-setnumber','f-name','f-parts','f-condition',
  'f-location','f-date','f-price','f-theme','f-year','f-minifigs','f-ean','f-note'];
```
Add `'f-list-price'`:
```javascript
const _FIELD_IDS = ['f-brand','f-setnumber','f-name','f-parts','f-condition',
  'f-location','f-date','f-price','f-list-price','f-theme','f-year','f-minifigs','f-ean','f-note'];
```

- [ ] **Step 4: Verify the page renders**

Run: `.venv/bin/pytest -v`
Expected: 98 passed (no test changes).

Server smoke check (start a temp uvicorn on a non-clashing port):
```
cd /Users/hhalfpap/git/projects/own/brickset-tracker && .venv/bin/uvicorn main:app --port 8129
```
Run with `run_in_background: true`. Then:
```
curl -s http://localhost:8129/add | grep -E "(f-list-price|copy-list-to-price)" | head -5
```
Expect both `f-list-price` and `copy-list-to-price` references in the HTML.

Kill the server: `pkill -f "port 8129"`.

- [ ] **Step 5: Commit**

```
git add templates/add.html
git commit -m "$(cat <<'EOF'
feat(ui): add list_price field + copy button on add form

New list_price input above price_paid. Inline copy button next to
price_paid copies the list_price value into it — covers the common
case of paying retail without forcing the user to type the same
number twice. applyPrefill map and language-switch state array
extended to cover the new field.
EOF
)"
```

---

### Task 7: Same field + copy button in `templates/edit.html`

**Files:**
- Modify: `templates/edit.html`

- [ ] **Step 1: Add the new field above `price_paid`**

In `templates/edit.html`, find the `price_paid` field (around line 88):
```html
    <div class="field">
      <label for="f-price">{{ t('add.price_paid') }}</label>
      <input type="text" inputmode="decimal" id="f-price" name="price_paid"
             value="{{ set.price_paid or '' }}" style="font-family:var(--font-mono)">
    </div>
```

Replace with:
```html
    <div class="field">
      <label for="f-list-price">{{ t('add.list_price') }}</label>
      <input type="text" inputmode="decimal" id="f-list-price" name="list_price"
             value="{{ set.list_price or '' }}" style="font-family:var(--font-mono)">
    </div>

    <div class="field">
      <label for="f-price">{{ t('add.price_paid') }}</label>
      <div style="display:flex;gap:var(--sp-2);align-items:center">
        <input type="text" inputmode="decimal" id="f-price" name="price_paid"
               value="{{ set.price_paid or '' }}" style="font-family:var(--font-mono);flex:1">
        <button type="button" class="btn btn-ghost btn-sm" id="copy-list-to-price"
                onclick="document.getElementById('f-price').value = document.getElementById('f-list-price').value"
                title="{{ t('add.copy_from_list_price') }}">←</button>
      </div>
    </div>
```

Note the source for the value attribute is `set.list_price` (the edit page passes `set` not `prefill`).

- [ ] **Step 2: Update the `applyPrefill` map**

Find the `applyPrefill` function (around line 228). The current map includes `price_paid: 'f-price'`. Add `list_price: 'f-list-price'`:
```javascript
  const map = {
    brand: 'f-brand', set_number: 'f-setnumber', name: 'f-name',
    part_count: 'f-parts', theme: 'f-theme', release_year: 'f-year',
    price_paid: 'f-price', list_price: 'f-list-price', ean: 'f-ean', note: 'f-note',
    condition: 'f-condition', location: 'f-location', date_of_purchase: 'f-date',
  };
```

- [ ] **Step 3: Update the language-switch state-persistence array**

Find `_FIELD_IDS` (around line 320):
```javascript
const _FIELD_IDS = ['f-brand','f-setnumber','f-name','f-parts','f-condition',
  'f-location','f-date','f-price','f-theme','f-year','f-minifigs','f-ean','f-note'];
```
Add `'f-list-price'`:
```javascript
const _FIELD_IDS = ['f-brand','f-setnumber','f-name','f-parts','f-condition',
  'f-location','f-date','f-price','f-list-price','f-theme','f-year','f-minifigs','f-ean','f-note'];
```

- [ ] **Step 4: Verify**

Run: `.venv/bin/pytest -v`
Expected: 98 passed.

Smoke: start a temp uvicorn and curl `/sets/4/edit` (or any existing set id; pick one from your DB):
```
cd /Users/hhalfpap/git/projects/own/brickset-tracker && .venv/bin/uvicorn main:app --port 8130
```
Run with `run_in_background: true`. Then:
```
curl -s http://localhost:8130/sets/1/edit | grep -E "(f-list-price|copy-list-to-price)" | head -5
```
Expect both references in the HTML.

Kill: `pkill -f "port 8130"`.

- [ ] **Step 5: Commit**

```
git add templates/edit.html
git commit -m "$(cat <<'EOF'
feat(ui): add list_price field + copy button on edit form

Same field + copy button shape as add.html. value="{{ set.list_price }}"
because edit passes the existing record as set (not prefill).
EOF
)"
```

---

### Task 8: Conditional list-view display in `templates/_results_partial.html`

**Files:**
- Modify: `templates/_results_partial.html`

- [ ] **Step 1: Replace the price rendering block**

In `templates/_results_partial.html`, find the existing price-paid rendering (around line 57):
```jinja
        {% if s.price_paid %}
          <span>{{ "%.2f"|format(s.price_paid) }} €</span>
        {% endif %}
```

Replace with the new conditional logic:
```jinja
        {% if s.price_paid %}
          <span>
            {{ "%.2f"|format(s.price_paid) }} €
            {% if s.list_price and s.list_price != s.price_paid %}
              <span class="text-muted">(von {{ "%.2f"|format(s.list_price) }} €)</span>
            {% endif %}
          </span>
        {% elif s.list_price %}
          <span><span class="text-muted">{{ t('list.price_list') }}</span> {{ "%.2f"|format(s.list_price) }} €</span>
        {% endif %}
```

Behaviour matrix this implements (matches the spec):

| price_paid | list_price | Output |
|---|---|---|
| 219.99 | 219.99 | `219,99 €` |
| 0.00 | 199.00 | `0,00 € (von 199,00 €)` |
| 150.00 | 199.00 | `150,00 € (von 199,00 €)` |
| 219.99 | NULL | `219,99 €` |
| NULL | 199.00 | `Listenpreis: 199,00 €` (DE) / `List price: 199,00 €` (EN) |
| NULL | NULL | (nothing) |

The "(von X €)" parenthetical is unlocalized (short, universal). The "Listenpreis:" / "List price:" prefix uses the new `list.price_list` i18n key (added in Task 9).

- [ ] **Step 2: Verify**

Run: `.venv/bin/pytest -v`
Expected: 98 passed.

Smoke check: start uvicorn and inspect the list page:
```
cd /Users/hhalfpap/git/projects/own/brickset-tracker && .venv/bin/uvicorn main:app --port 8131
```
Run with `run_in_background: true`. Then:
```
curl -s http://localhost:8131/ | grep -E "von|text-muted|list_price|list.price_list" | head -10
```
The output depends on what rows exist in your DB. For now the new keys probably render as `list.price_list` literal (Task 9 adds the i18n).

Kill: `pkill -f "port 8131"`.

- [ ] **Step 3: Commit**

```
git add templates/_results_partial.html
git commit -m "$(cat <<'EOF'
feat(ui): show list_price on list cards when it differs from price_paid

Pantasy giveaway case renders as '0,00 € (von 199,00 €)'. Same-price
case (paid retail) renders as a single value. Rows with only list_price
known render as 'Listenpreis: X €' so freshly imported rows still
surface their retail price.
EOF
)"
```

---

## Phase 5 — Polish + verification

### Task 9: Add i18n keys

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/de.json`

- [ ] **Step 1: Add to `locales/en.json`**

In the `"add"` object, add two new keys:
```json
    "list_price":           "List Price (€)",
    "copy_from_list_price": "Copy from list price",
```
Place them after `"price_paid"`. Preserve JSON-comma rules — the previous key must have a trailing comma; the last key in the object must NOT.

In the `"list"` object, add one new key:
```json
    "price_list":     "List price:",
```

- [ ] **Step 2: Add to `locales/de.json`**

In the `"add"` object:
```json
    "list_price":           "Listenpreis (€)",
    "copy_from_list_price": "Listenpreis übernehmen",
```

In the `"list"` object:
```json
    "price_list":     "Listenpreis:",
```

- [ ] **Step 3: Validate JSON + key parity**

Run:
```
.venv/bin/python -c "
import json
en = json.load(open('locales/en.json'))
de = json.load(open('locales/de.json'))
assert 'list_price' in en['add'] and 'list_price' in de['add']
assert 'copy_from_list_price' in en['add'] and 'copy_from_list_price' in de['add']
assert 'price_list' in en['list'] and 'price_list' in de['list']
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 4: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 98 passed.

- [ ] **Step 5: Commit**

```
git add locales/en.json locales/de.json
git commit -m "$(cat <<'EOF'
feat(i18n): add list_price translation keys

3 new keys: add.list_price (form label), add.copy_from_list_price
(button tooltip), list.price_list (list-card prefix). EN and DE in
parity.
EOF
)"
```

---

### Task 10: Final end-to-end manual verification

**Files:** none modified.

Walk through these scenarios in `http://localhost:8123/` (restart the server first to pick up the new code) in both DE and EN.

- [ ] **Step 1: Restart server**

If the user's existing :8123 server is running, the auto-reload should have picked up everything. To be safe, kill and restart:
```
pkill -f "uvicorn main:app --port 8123" 2>/dev/null
.venv/bin/uvicorn main:app --port 8123 --reload
```
Run with `run_in_background: true`. Wait for `Server ready`.

- [ ] **Step 2: Schema migration sanity**

The user's existing 33-row DB should pick up the new column without data loss:
```
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('data/brickset.db')
conn.row_factory = sqlite3.Row
cols = {r['name'] for r in conn.execute(\"PRAGMA table_info(sets)\").fetchall()}
assert 'list_price' in cols, 'list_price column missing!'
n = conn.execute('SELECT COUNT(*) AS n FROM sets').fetchone()['n']
n_filled = conn.execute('SELECT COUNT(*) AS n FROM sets WHERE list_price IS NOT NULL').fetchone()['n']
print(f'Rows: {n}, with list_price set: {n_filled}')
"
```
Expect: rows count matches the user's collection size (~33), list_price filled = 0.

- [ ] **Step 3: Add a new set with lookup**

In the browser, go to `/add`. Enter the Pantasy 85036 setup or any LEGO setnumber. Click "Fetch Data".

Verify:
- `f-list-price` is populated with the scraped/Brickset retail price
- `f-price` (price paid) is STILL EMPTY
- Clicking the `←` button copies list_price into price_paid

- [ ] **Step 4: Manual price-paid override**

For the Pantasy giveaway scenario:
- Lookup the set → list_price = 199 (or whatever the retail is)
- Leave the copy button alone
- Type `0` into price_paid
- Save

Then on the collection list, the row should display `0,00 € (von 199,00 €)` (or `(von 199.00 €)` in EN).

- [ ] **Step 5: Edit existing row to backfill list_price**

Open `/sets/{id}/edit` for one of the 33 existing rows (e.g., the Magical Unicorn). The list_price field should be empty.

Click "Fetch Data" at the top → list_price populates from the lookup. Save. The row's list-view rendering should now reflect both prices according to the matrix.

- [ ] **Step 6: Both prices the same**

A row where price_paid == list_price should render as just the single value, no parenthetical. Verify with any existing row where you didn't get a discount.

- [ ] **Step 7: Brickset import still works**

`/import/brickset` → fetch → commit. The newly-imported rows should have list_price populated from Brickset's LEGOCom.DE.retailPrice (where Brickset has it) and price_paid blank.

- [ ] **Step 8: Language toggle**

Switch DE ↔ EN at any point. The form labels translate (`List Price (€)` / `Listenpreis (€)`). The list-view prefix translates (`List price:` / `Listenpreis:`). The "(von X €)" stays in German across both — by design.

- [ ] **Step 9: Mark verification commit**

```
git commit --allow-empty -m "$(cat <<'EOF'
chore: verify list_price feature end-to-end

All scenarios in plan Task 10 pass in both DE and EN. The existing
33-row production DB picks up the new column without data loss;
price_paid stays blank on lookup; copy button works; conditional
list-view display correct across all six matrix cases.
EOF
)"
```

---

## Done

Iteration 3.7 complete. The collection now tracks retail (`list_price`) and actual paid (`price_paid`) as separate, independently-edited values. The Pantasy giveaway case ("price_paid: €0, list_price: €199") is the canonical record-shape this enables.

Next on the V1 path: **Iteration 4 (details view) → code review → Phase T (LaunchAgent)**.
