# List Price Field — Design

**Status:** Approved 2026-05-17
**Project:** brickset-tracker
**Iteration:** 3.7 (interstitial between Iteration 3.5 Brickset import and Iteration 4 details view)

## Goal

Add a `list_price` field that records the manufacturer/retail price of a set, separate from `price_paid` (what the user actually paid). Resolves the long-standing semantic confusion where the scraped Listenpreis was stored as `price_paid` — wrong for any set bought at a discount, on sale, or received as a gift.

## Motivating Example

User received a Pantasy set (number 85036) as a free giveaway for participating in a survey. Retail is €199 but actual price paid was €0. With a single price field the system can either lie ("price paid: €199") or lose value information ("price paid: €0, retail unknown"). With both fields the record is complete.

## Behaviour Summary

- **Forms (add + edit):** new `list_price` input directly above `price_paid`, with a small `← copy` button that copies list price → price paid.
- **Lookup auto-fill:** only `list_price` is auto-filled from scrape/API; `price_paid` stays blank until the user enters it.
- **List view:** `list_price` shown beside `price_paid` only when they differ; otherwise hidden.
- **Existing rows:** stay with `list_price = NULL` until the user touches them; no bulk backfill.

## Schema Change

New column in `sets`:

```sql
list_price REAL
```

Migration in `execution/db.py:init_db()` — additive `ALTER TABLE` wrapped in try/except so the function stays idempotent:

```python
try:
    conn.execute("ALTER TABLE sets ADD COLUMN list_price REAL")
except sqlite3.OperationalError:
    pass  # Already added on a prior run
```

No data loss. Existing rows initialise to `NULL`. No external migration framework needed.

## Data Sources

### merlinssteine.de (already extracted)

The scraper already parses the page's "Listenpreis:" line. Today the result is keyed `"price"` and the lookup router maps it to `price_paid` — semantically wrong. Two renames fix it:

- `execution/scraper.py`: result dict key `"price"` → `"list_price"`.
- `navigation/lookup_router.py`: in `_merge_from_merlinssteine`, map `result["list_price"] → prefill["list_price"]` (replacing the existing `price → price_paid` mapping).

### Brickset (newly extracted)

Brickset's getSets response nests retail prices under `LEGOCom`, keyed by country code. For a German user, the relevant value is `s["LEGOCom"]["DE"]["retailPrice"]` (in EUR). Example response shape:

```json
"LEGOCom": {
  "US": {"retailPrice": 99.99, ...},
  "UK": {"retailPrice": 89.99, ...},
  "CA": {"retailPrice": 129.99, ...},
  "DE": {"retailPrice": 99.99, "dateFirstAvailable": "...", "dateLastAvailable": "..."}
}
```

Extraction:

- `execution/brickset.py`: in `_map_set()`, add a defensive extractor `s.get("LEGOCom", {}).get("DE", {}).get("retailPrice")` mapped to `list_price`. Use `None` when any segment of the chain is missing — common for old, regional, or unreleased sets.
- `navigation/lookup_router.py`: in `_merge_from_brickset`, add `list_price` to the gap-fill map (only sets if merlinssteine didn't already provide one).

Other regions' retail prices (`US`, `UK`, `CA`) are intentionally ignored — the user is in Germany and the EUR figure is what's meaningful for them.

Precedence stays consistent with the existing pattern: merlinssteine wins where it has data; Brickset fills gaps. Both sources tried for LEGO; only merlinssteine for non-LEGO.

## Form UI (add + edit)

The two price fields appear in this order, side by side in the existing form grid:

```
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ LIST PRICE (€)               │  │ PRICE PAID (€)               │
│ [ 199.00          ]   ← copy │  │ [ 0.00                     ] │
└──────────────────────────────┘  └──────────────────────────────┘
```

- Same input style as `price_paid`: `type="text"`, `inputmode="decimal"`, mono font, accepts both German (`199,00`) and dot-decimal (`199.00`).
- `← copy` is a small `btn btn-ghost btn-sm` button placed inside the list-price field's container. Clicking it copies `#f-list-price.value` into `#f-price.value`. Pure client-side JS, no round-trip.
- After "Fetch Data": `#f-list-price` is populated from the lookup; `#f-price` stays unchanged (blank by default).

## List View Display

In `templates/_results_partial.html`, the existing single-line price rendering becomes conditional:

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

Behaviour matrix:

| price_paid | list_price | What renders |
|---|---|---|
| 219.99 | 219.99 | `219,99 €` |
| 0.00 | 199.00 | `0,00 € (von 199,00 €)` — Pantasy case |
| 150.00 | 199.00 | `150,00 € (von 199,00 €)` — discount |
| 219.99 | NULL | `219,99 €` — existing row, not yet re-fetched |
| NULL | 199.00 | `Listenpreis: 199,00 €` — just imported |
| NULL | NULL | (nothing rendered) |

The "(von X €)" parenthetical stays unlocalized — short, universally readable, and visually clear in both German and English contexts. Only `Listenpreis:` (the row-5 prefix) needs translation.

## set_manager Plumbing

`navigation/set_manager.py` — three functions extended to read/write `list_price`:

- `save_set(data, ...)` — write `_float(data.get("list_price"))` into the INSERT column list
- `update_set(set_id, data, ...)` — same in the UPDATE column list
- `get_set(set_id)` / `_row_to_dict(row)` — already reads all columns; the new column flows through `SELECT *` (no per-column changes needed since `_row_to_dict` is permissive)

The existing `_float` helper already handles German-or-dot decimal parsing — no new parser needed.

## i18n Keys

New keys in both `locales/en.json` and `locales/de.json`:

| Key | EN | DE |
|---|---|---|
| `add.list_price` | `List Price (€)` | `Listenpreis (€)` |
| `add.copy_from_list_price` | `← copy from list price` | `← Listenpreis übernehmen` |
| `list.price_list` | `List price:` | `Listenpreis:` |

## Tests

Backend tests added:

- Scraper rename: existing scraper test (if present) updated to expect `list_price` key. If no scraper unit test exists yet, no new test needed — the rename is verified end-to-end via the route tests.
- Brickset `_map_set` extracts `EUPrice` as `list_price` — extend the existing `_map_set` / `_map_owned_set` tests with a fixture that includes `EUPrice` in the raw Brickset payload.
- `lookup_router._flow1` populates `list_price` (from both merlinssteine and Brickset paths) and does NOT populate `price_paid` — small end-to-end test using existing mock infrastructure.
- `save_set` and `update_set` round-trip `list_price` correctly (factory-based test).

Frontend verified manually:

- Copy button on add page copies value into `price_paid`
- Copy button on edit page same
- List view shows `(von …)` for differing values
- List view shows `Listenpreis: …` when only list_price is set
- List view hides both when both are NULL

## Out of Scope

- Bulk backfill of the 33 existing rows. User backfills on-demand via the edit page's "Fetch Data" button (existing flow).
- Currency other than EUR. The schema column is currency-agnostic (REAL) but the form labels and display assume EUR throughout the project.
- Historical price tracking (price changes over time). One value per set, last-write-wins.
- Per-row currency conversion using Brickset's USPrice/UKPrice/caPrice fields. EU user → EUPrice only.

## Files Touched

| File | Change |
|---|---|
| `execution/db.py` | Idempotent `ALTER TABLE` in `init_db()` |
| `execution/scraper.py` | Rename result key `price` → `list_price` |
| `execution/brickset.py` | Extract `EUPrice` → `list_price` in `_map_set()` |
| `navigation/lookup_router.py` | `_merge_from_merlinssteine` writes `list_price`; `_merge_from_brickset` gap-fills `list_price`; both stop touching `price_paid` |
| `navigation/set_manager.py` | `save_set` + `update_set` handle the new column |
| `templates/add.html` | New `#f-list-price` input + copy button |
| `templates/edit.html` | Same |
| `templates/_results_partial.html` | Conditional list-view display |
| `locales/en.json`, `locales/de.json` | 3 new keys |
| `static/style.css` | No change (uses existing `.text-muted` utility class) |
| `tests/test_*` | Brickset `_map_set` EUPrice test, lookup_router list_price test, set_manager round-trip test |

No new dependencies. No new MCP servers. No DB migration framework — just the additive ALTER TABLE.

## Open Questions

None remaining. All decisions confirmed via brainstorming dialogue 2026-05-17:

- **Auto-fill behaviour:** only `list_price` (option A); `price_paid` stays blank. Copy button mitigates the common-case typing burden.
- **List view display:** only show `list_price` when it differs from `price_paid` (option C).
- **Existing rows:** stay NULL (option A); user backfills via existing edit-page "Fetch Data" flow.
