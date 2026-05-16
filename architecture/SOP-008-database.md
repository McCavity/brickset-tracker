# SOP-008 — Database

**Layer:** Tool (execution)
**Goal:** Define the SQLite schema, initialisation procedure, and query patterns for all data operations.

---

## File Location
```
data/brickset.db   ← created automatically on first startup
```

---

## Schema

```sql
-- Main collection
CREATE TABLE IF NOT EXISTS sets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ean              TEXT,
    brand            TEXT    NOT NULL,
    set_number       TEXT    NOT NULL,
    name             TEXT    NOT NULL,
    part_count       INTEGER NOT NULL,
    condition        TEXT,                       -- German canonical condition string
    location         TEXT,
    date_of_purchase TEXT,                       -- ISO date "YYYY-MM-DD"; default NOW() for complete records
    note             TEXT,
    theme            TEXT,
    release_year     INTEGER,
    web_images       TEXT,                       -- JSON array of CDN/web URLs
    own_photos       TEXT,                       -- JSON array of relative local paths
    minifigs         INTEGER,
    price_paid       REAL,
    brickset_set_id  INTEGER,                    -- cached Brickset internal setID (LEGO only)
    status           TEXT    NOT NULL DEFAULT 'draft',  -- 'complete' | 'draft'
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- EAN → (brand, set_number) cache
CREATE TABLE IF NOT EXISTS ean_cache (
    ean          TEXT PRIMARY KEY,
    brand        TEXT NOT NULL,
    set_number   TEXT NOT NULL,
    source       TEXT,                           -- 'upcitemdb' | 'opf' | 'manual'
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Daily quota tracking for external services
CREATE TABLE IF NOT EXISTS scrape_quota (
    service      TEXT NOT NULL,
    date         TEXT NOT NULL,                  -- ISO date "YYYY-MM-DD"
    count        INTEGER DEFAULT 0,
    PRIMARY KEY (service, date)
);

-- Indexes for list view sorting performance
CREATE INDEX IF NOT EXISTS idx_sets_brand        ON sets(brand);
CREATE INDEX IF NOT EXISTS idx_sets_date         ON sets(date_of_purchase);
CREATE INDEX IF NOT EXISTS idx_sets_status       ON sets(status);
```

---

## Initialisation

On every app startup:
1. Connect to `data/brickset.db` (create if absent).
2. Run all `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` statements.
3. Run `SOP-005 Operation C` (staging folder cleanup).
4. Return connection to the app.

---

## Key Query Patterns

### Insert new set
```sql
INSERT INTO sets (ean, brand, set_number, name, part_count, condition, location,
                  date_of_purchase, note, theme, release_year, web_images, own_photos,
                  minifigs, price_paid, brickset_set_id, status)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```
`date_of_purchase` defaults to `date('now')` in Python when status='complete' and no date provided.

### Duplicate check
```sql
SELECT id, condition, note, date_of_purchase
FROM sets
WHERE brand = ? AND set_number = ?
ORDER BY date_of_purchase DESC
```

### List view (sortable)
```sql
SELECT id, brand, set_number, name, part_count, condition, date_of_purchase,
       price_paid, status, own_photos, web_images
FROM sets
ORDER BY {sort_column} {sort_direction}
-- sort_column validated against allowlist before interpolation
-- allowlist: date_of_purchase, name, brand, part_count, price_paid, created_at
```

### Brickset qtyOwned count (complete records only)
```sql
SELECT COUNT(*) FROM sets
WHERE brand = 'LEGO' AND set_number = ? AND status = 'complete'
```

---

## Data Integrity Rules

- `sort_column` is **always** validated against the allowlist before string interpolation — never accept raw user input as a column name.
- `web_images` and `own_photos` are stored as JSON strings; parsed in Python, never in SQL.
- `updated_at` is updated via Python (not a DB trigger) on every edit to keep logic visible.
- No foreign keys — SQLite FK support requires explicit enabling and adds complexity for marginal gain at this scale.
