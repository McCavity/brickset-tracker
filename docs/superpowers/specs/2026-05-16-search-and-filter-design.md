# Iteration 3 — Search + Filter — Design

**Status:** Approved 2026-05-16
**Project:** brickset-tracker
**Iteration:** 3 (of the V1 plan in `CLAUDE.md`)

## Goal

Add search and faceted filtering to the collection list view at `/`, so the user can quickly find sets across a small-but-growing personal collection.

## UI Structure

Top of the `/` collection page becomes:

```
┌─────────────────────────────────────────────────────┐
│  My Collection                       [+ Add Set]    │  ← existing header
├─────────────────────────────────────────────────────┤
│  🔍 [Search across all fields…………]   [✕ clear]      │  ← new
├─────────────────────────────────────────────────────┤
│  ▸ Filters (3 active)   ·   Clear all               │  ← new, collapsible
│  ┌─ when expanded ──────────────────────────────┐   │
│  │ Brand:      ☑ LEGO (12)  ☐ BlueBrixx (3)     │   │
│  │ Condition:  ☑ Gebaut (8)  ☐ OVP (4)          │   │
│  │ Theme:      ☐ Star Wars (5)  ☐ City (2)      │   │
│  │ Status:     ☐ Draft (1)                      │   │
│  └──────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  Sort by: Date · Name · Brand · Parts · Price       │  ← unchanged
├─────────────────────────────────────────────────────┤
│  ✦ 15 of 23 sets shown                              │  ← new result count
│  [set cards…]                                       │
└─────────────────────────────────────────────────────┘
```

- Filter toggle shows `(N active)` only when ≥1 filter is set.
- Filter panel open/closed state saved to `localStorage['bst_filters_open']`. Default closed.
- Facets with 0 hits given the current *other* filters are hidden entirely.
- Result count line shown only when filters or search are active.

## Backend

### `navigation/set_manager.py`

Extend `get_sets()`:

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
```

- **Search (`q`)** matches `LIKE %q%` (case-insensitive) across: `name`, `brand`, `set_number`, `ean`, `theme`, `note`, `location`, `condition`, `release_year` (cast to text), `part_count` (cast to text).
- **Multi-select facets** combine as `OR` within a facet, `AND` across facets. E.g. picking LEGO + BlueBrixx + Gebaut means `(brand=LEGO OR brand=BlueBrixx) AND condition=Gebaut`.
- All params optional; empty list or `None` means "no filter on this dimension".
- One parameterized SQL query — no string interpolation of user input.

New companion function:

```python
def get_facet_counts(
    q: str | None = None,
    brands: list[str] | None = None,
    conditions: list[str] | None = None,
    themes: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """Returns {"brand": {"LEGO": 12, ...}, "condition": {...}, ...}"""
```

Counts each facet **ignoring its own filter** (standard faceted-search semantics) so checkboxes stay switchable. Four small queries, one per facet — instant for a collection of hundreds.

New helper for the "X of Y" display:

```python
def count_all_sets() -> int:
    """Total set count, ignoring all filters. For the result-count line."""
```

### `main.py`

Two routes:

```python
@app.get("/")
async def index(
    request: Request,
    sort: str = "date_of_purchase",
    dir: str = "DESC",
    q: str | None = None,
    brand: list[str] = Query(default=[]),       # repeated query param
    condition: list[str] = Query(default=[]),
    theme: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
):
    sets = get_sets(sort_by=sort, sort_dir=dir, q=q,
                    brands=brand, conditions=condition,
                    themes=theme, statuses=status)
    facets = get_facet_counts(q=q, brands=brand, conditions=condition,
                              themes=theme, statuses=status)
    total = count_all_sets()
    return templates.TemplateResponse(request, "index.html", context=_ctx(
        request, sets=sets, facets=facets, total=total,
        active_filters={"brand": brand, "condition": condition,
                        "theme": theme, "status": status},
        q=q or "", sort=sort, dir=dir,
    ))


@app.get("/api/sets/filter", response_class=HTMLResponse)
async def api_filter(
    request: Request,
    sort: str = "date_of_purchase",
    dir: str = "DESC",
    q: str | None = None,
    brand: list[str] = Query(default=[]),
    condition: list[str] = Query(default=[]),
    theme: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
):
    """Returns the results region (cards + count + empty state) as an HTML partial."""
    sets = get_sets(sort_by=sort, sort_dir=dir, q=q,
                    brands=brand, conditions=condition,
                    themes=theme, statuses=status)
    total = count_all_sets()
    return templates.TemplateResponse(request, "_results_partial.html", context=_ctx(
        request, sets=sets, total=total,
        active_filters={"brand": brand, "condition": condition,
                        "theme": theme, "status": status},
        q=q or "",
    ))
```

Note the naming convention: HTTP query params are **singular** (`brand`, `condition`, …) because FastAPI's `Query(default=[])` collects repeated singular params into a list. The `get_sets()` / `get_facet_counts()` Python args are **plural** (`brands`, `conditions`, …) because they receive a list. Both are intentional and idiomatic in their respective layers.

URL example: `/?q=dragon&brand=LEGO&brand=BlueBrixx&condition=gebaut&sort=name&dir=ASC`

- First load: server renders the page fully (back button, bookmarks, refresh all work natively).
- Filter changes after that hit `/api/sets/filter`; JS swaps the partial in. No flicker, no full reload.
- URL updated via `history.replaceState()` on every filter change so refresh and bookmarks capture the current view.

## Templates

### `templates/index.html` (restructured)

```html
{% extends "base.html" %}
{% block content %}
  {# Page header — unchanged #}
  {# Search row — new #}
  {# Filter panel — new, collapsible, uses `facets` + `active_filters` #}
  {# Sort bar — unchanged #}

  {# Results region — wrapped in <div id="results-region"> #}
  {% include "_results_partial.html" %}
{% endblock %}
```

### `templates/_results_partial.html` (new)

Contains:

- Result count line: `{{ sets|length }} of {{ total }} sets shown` (only when filters/search active)
- Empty state when filtered to zero: `No sets match these filters` + `Clear all filters` link
- Existing empty-collection state preserved (`No sets yet. Add your first set!`)
- The set-list / set-cards loop (moved from `index.html`)

### Frontend JS (in `index.html` `{% block scripts %}`)

- Debounced search input (250 ms) → fetch `/api/sets/filter?...`, swap `#results-region` innerHTML, `history.replaceState()` the new URL.
- Checkbox `onchange` → same flow, no debounce.
- Filter panel toggle stores open/closed state in `localStorage['bst_filters_open']`.
- `lucide.createIcons()` re-run after partial swap so card icons re-render.
- Sort bar links keep their current behaviour (full page navigation) — sort changes are infrequent enough not to need optimisation.

## i18n

New keys in `locales/de.json` and `locales/en.json`:

| Key | EN | DE |
|---|---|---|
| `list.search_placeholder` | `Search across all fields...` | `Alle Felder durchsuchen...` |
| `list.search_clear` | `Clear search` | `Suche löschen` |
| `list.filters` | `Filters` | `Filter` |
| `list.filters_active` | `{count} active` | `{count} aktiv` |
| `list.filter_clear_all` | `Clear all filters` | `Alle Filter zurücksetzen` |
| `list.facet_brand` | `Brand` | `Marke` |
| `list.facet_condition` | `Condition` | `Zustand` |
| `list.facet_theme` | `Theme` | `Thema` |
| `list.facet_status` | `Status` | `Status` |
| `list.status_complete` | `Complete` | `Vollständig` |
| `list.status_draft` | `Draft` | `Entwurf` |
| `list.results_count` | `{shown} of {total} sets` | `{shown} von {total} Sets` |
| `list.no_matches` | `No sets match these filters` | `Keine Sets entsprechen diesen Filtern` |

`list.empty` (already exists) keeps its current meaning: "collection is genuinely empty".

## Edge Cases & Behaviour

- **Empty search box + no filters** — show entire collection, no result-count line (matches current behaviour).
- **Filter selects zero rows** — `No sets match these filters` + `Clear all filters` link.
- **Facet with zero hits given other filters** — hidden entirely. Reappears once other filters are loosened.
- **Facet group with zero options** — entire facet group (label + checkboxes) hidden. E.g. if no set has a `theme` set, the whole "Theme" row disappears.
- **NULL handling** — `condition`, `theme`, and `status` can be null in the DB. NULL values are not shown as a facet option (since "no condition" isn't meaningful to filter on). NULL rows still appear in unfiltered results.
- **Drafts** — included in results by default. Status facet lets you isolate them. The existing yellow "Draft" badge on cards stays.
- **Search semantics** — case-insensitive substring match. Implementation registers a Python function `py_lower` on the SQLite connection (in `execution/db.py`: `conn.create_function("py_lower", 1, lambda s: s.lower() if s else s)`) and queries with `py_lower(column) LIKE py_lower(?)`. This handles Unicode/umlauts correctly (`Möbel` ↔ `möbel`), unlike SQLite's built-in `LOWER()` which is ASCII-only. The query parameter is bound as `f"%{q.lower()}%"`. No multi-word AND logic for V1 (`"star city"` matches the literal substring "star city", not sets containing both words separately). Can be revisited in V1.1.
- **URL state on first load** — if you arrive with `?q=foo&brand=LEGO`, the search input is pre-filled, the LEGO checkbox is pre-ticked, and the filter panel auto-opens because filters are active. Otherwise panel honours `localStorage`.
- **Sort + filter interact** — clicking a sort header preserves current filter/search in URL. Filter changes preserve current sort.
- **Language switch** — current `?q=...&brand=...` URL is carried in the existing `next` hidden field, so switching language keeps the filtered view.
- **Server-side sanitisation** — `q` length capped at 200 chars; unknown brand/condition/theme/status values silently dropped (no error).

## Out of Scope for Iteration 3

Recorded here so they can be revisited intentionally in V1.1 or later:

- Range filters for `release_year`, `price_paid`, `part_count`, `minifigs`
- Multi-word AND search semantics
- Fuzzy / typo-tolerant search
- Saved searches / named views
- A `location` facet
- Server-side pagination
- A "has photos" / "no photos" filter

## Files Touched

| File | Change |
|---|---|
| `execution/db.py` | Register `py_lower` SQLite function for Unicode-aware case-insensitive search |
| `navigation/set_manager.py` | Extend `get_sets()`, add `get_facet_counts()`, add `count_all_sets()` |
| `main.py` | Extend `/` route, add `GET /api/sets/filter` route |
| `templates/index.html` | Restructure: search row + filter panel; move card loop into partial |
| `templates/_results_partial.html` | **New** — result count, empty-when-filtered state, card loop |
| `static/style.css` | New styles for search bar, filter panel, facet checkboxes, result-count line |
| `locales/de.json`, `locales/en.json` | Add 13 new keys |

No DB migrations. No new dependencies.
