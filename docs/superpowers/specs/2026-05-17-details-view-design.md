# Details View — Design

**Status:** Approved 2026-05-17
**Project:** brickset-tracker
**Iteration:** 4

## Goal

Add a canonical per-set page at `/sets/{id}` — a calm read-only inspection view with all metadata visible at once, prominent photos, and obvious paths to edit/delete/sync/external-source actions. Becomes the click destination for set names on the collection list.

## User Flow

1. From the collection list at `/`, the set name on each card is now a link. Click → `/sets/{id}`.
2. The details page renders the set: action bar at top, photos in the left column, metadata in the right column. Click any thumbnail → fullscreen lightbox. Press Esc or click the backdrop → close lightbox.
3. Top action bar offers: ← Back to collection, Edit (→ `/sets/{id}/edit`), Delete (existing modal), Sync (Brickset).
4. External links section in the right column: links to the set's Brickset page (LEGO only, when `brickset_set_id` is known) and merlinssteine.de page (always rendered).

## URL + Route

- `GET /sets/{id}` — new route.
- Calls `get_set(id)`; if missing, `RedirectResponse("/", status_code=303)` (matches existing edit-page 404 behaviour).
- Page title: `{name} ({brand} {set_number}) · Brickset Tracker`.

## Layout

Responsive two-column grid on desktop, single column on mobile (CSS-only, one media query at `~768px`).

```
┌─────────────────────────────────────────────────────────────────────┐
│ ← Back to collection                  [ Edit ]  [ Delete ]  [Sync↻] │
├─────────────────────────────────────────────────────────────────────┤
│  LEGO · 10298                                                       │
│  Vespa 125                                              [✓ Built]   │
│                                                          [Star Wars]│
├──────────────────────────────────┬──────────────────────────────────┤
│  ┌─────────────────────────┐     │  Numbers                         │
│  │     [main own photo]    │     │  ───────                         │
│  └─────────────────────────┘     │  Parts:        1,106             │
│  [thumb] [thumb] [thumb]         │  Minifigs:     —                 │
│                                  │  Released:     2022              │
│  ── Web images ──                │  Purchased:    2026-04-12        │
│  [web img] [web img]             │  Price paid:   99,99 €           │
│                                  │  List price:   99,99 €           │
│                                  │  EAN:          5702016912661     │
│                                  │                                  │
│                                  │  Where & how                     │
│                                  │  ────────────                    │
│                                  │  Location:     Wohnzimmer        │
│                                  │  Theme:        Creator Expert    │
│                                  │  Note:         (multi-line text) │
│                                  │                                  │
│                                  │  External links                  │
│                                  │  ──────────────                  │
│                                  │  ↗ Brickset page                 │
│                                  │  ↗ merlinssteine.de page         │
└──────────────────────────────────┴──────────────────────────────────┘
```

Responsive behaviour:
- ≥768px: two-column grid (`grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)`)
- <768px: single column stacked — header → photos → metadata → external links

The top action bar stays full-width above the columns on all sizes.

## Header

Two-line:
- **Kicker:** `{brand | upper} · <span class="mono">{set_number}</span>` — matches the list-card kicker style.
- **Name (h1):** the set's `name`, with the draft badge and condition tag floated right (only rendered when present).

## Action Bar

Above the header. Full-width, left-justified back link, right-justified action buttons.

- **← Back to collection** — `<a href="/" class="btn btn-ghost">` with `data-lucide="arrow-left"` icon. Plain link; browser back button works equivalently.
- **Edit** — `<a href="/sets/{id}/edit" class="btn btn-secondary">` with pencil icon.
- **Delete** — `<button class="btn btn-ghost" onclick="openDeleteModal({{ s.id }}, '{{ s.name | replace("'", "\\'") }}')">` with trash icon. Reuses the existing modal in `base.html`.
- **Sync** — `<button class="btn btn-ghost" onclick="syncBrickset({{ s.id }}, this)">` with refresh-cw icon. Only rendered when `s.brickset_set_id is not none and s.brand | lower == 'lego'` (Jinja2 uses lowercase `and`).

`syncBrickset()` is moved from `index.html` to `base.html` so both list and details views share it without duplication. ~10 lines moved; no behaviour change.

## Photo Gallery (left column)

Layout:
1. **Main image** (large, ~400×400 maxed at column width): first `own_photo` if any, else first `web_image`, else the SVG brick placeholder reused from `_results_partial.html`.
2. **Thumbnail strip** (80×80 each): all `own_photos`. Each is clickable → lightbox.
3. If both `own_photos` AND `web_images` exist, render a divider labelled `{{ t('details.web_images_label') }}` (e.g. "Web images") followed by the web image thumbnails.
4. If only `web_images` exist (no own photos), the main image is the first web image, all thumbnails are web images, no divider needed.
5. All web images go through the existing `/api/proxy-image?url=...` endpoint.

## Lightbox

Vanilla JS + CSS, no library. Inline in `details.html`'s `{% block scripts %}`.

- Click any thumbnail or the main image → fullscreen overlay opens
- Overlay: `position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 200;`, image centered with `max-width: 90vw; max-height: 90vh; object-fit: contain;`
- Click backdrop (anywhere outside image) → close
- Press Esc → close
- If active photo set has more than one photo, arrow keys (←/→) navigate. Own photos and web images are treated as separate lists; clicking an own photo lets you cycle through own photos only, same for web.

Approximate code budget: ~40 lines CSS + ~30 lines JS, all inline.

## Metadata Sections (right column)

Three sections, each rendered only if it has at least one non-empty field:

### Numbers
Definition list of: `part_count`, `minifigs`, `release_year`, `date_of_purchase`, `price_paid`, `list_price`, `ean`. Each entry hidden if its value is null/empty. Format `part_count` as German thousands (`1.106`); prices as `%.2f €`.

### Where & how
Definition list of: `location`, `theme`, `note`. Note is rendered with `white-space: pre-wrap` to preserve line breaks.

### External links
- **Brickset page** — only when `brickset_set_id is not none`. URL: `https://brickset.com/sets/{set_number}-1/`. Opens in new tab (`target="_blank" rel="noopener"`). Lucide `external-link` icon.
- **merlinssteine.de page** — always rendered. URL: `https://www.merlinssteine.de/sets/{brand_to_slug(brand)}-{set_number.lower()}/`. Same target + icon.

Both URLs are computed in the route handler (not the template) and passed into the context as plain strings. This keeps templates dumb and avoids registering `brand_to_slug` as a Jinja2 global.

If neither URL applies (impossible today since merlinssteine link is unconditional, but defensive), the section header is hidden.

## Set-Name Link on List Cards

In `templates/_results_partial.html`, the existing `.set-card__name` div content is wrapped in a link:

```html
<a href="/sets/{{ s.id }}" class="set-card__name-link" title="{{ s.name }}">
  <div class="set-card__name">{{ s.name }}</div>
</a>
```

New CSS:
```css
.set-card__name-link { color: inherit; text-decoration: none; display: block; }
.set-card__name-link:hover .set-card__name {
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  color: var(--accent);
}
```

The pencil/trash/sync icons in `.set-card__actions` remain independently clickable; their positioning is unchanged.

## i18n Keys

17 new keys under `details.*` in both `locales/en.json` and `locales/de.json`. EN + DE in parity.

| Key | EN | DE |
|---|---|---|
| `details.back` | `← Back to collection` | `← Zurück zur Sammlung` |
| `details.section_numbers` | `Numbers` | `Zahlen` |
| `details.section_where` | `Where & how` | `Wo & wie` |
| `details.section_external` | `External links` | `Externe Links` |
| `details.web_images_label` | `Web images` | `Web-Bilder` |
| `details.field_parts` | `Parts:` | `Teile:` |
| `details.field_minifigs` | `Minifigs:` | `Minifiguren:` |
| `details.field_released` | `Released:` | `Erschienen:` |
| `details.field_purchased` | `Purchased:` | `Gekauft:` |
| `details.field_price_paid` | `Price paid:` | `Kaufpreis:` |
| `details.field_list_price` | `List price:` | `Listenpreis:` |
| `details.field_ean` | `EAN:` | `EAN:` |
| `details.field_location` | `Location:` | `Standort:` |
| `details.field_theme` | `Theme:` | `Thema:` |
| `details.field_note` | `Note:` | `Notiz:` |
| `details.link_brickset` | `Brickset page` | `Brickset-Seite` |
| `details.link_merlinssteine` | `merlinssteine.de page` | `merlinssteine.de-Seite` |

## Tests

- `tests/test_details_route.py` (new):
  - 200 + HTML when set exists
  - 303 redirect to `/` when set doesn't exist
  - Set name, set number, brand all present in HTML
  - Action bar links present (Edit URL, Delete trigger, Sync button only for LEGO with brickset_set_id)
  - merlinssteine link always present
  - Brickset link present only when `brickset_set_id is not none`

Frontend (lightbox, hover, responsive layout) verified manually.

## Out of Scope

- Editing fields inline on the details page (deliberate — details stays read-only; `/edit` is the editor)
- Carousel/swipe gestures in the lightbox (arrow keys are enough)
- Print-friendly stylesheet (defer to code review)
- "History" of price/condition changes over time
- Brand-to-slug user-configurable mapping (parked as Iteration 4.5)

## Files Touched

| File | Change |
|---|---|
| `main.py` | New `GET /sets/{id}` route; computes Brickset + merlinssteine URLs; renders `details.html` |
| `templates/details.html` | **New** — full page: header, action bar, two-column grid, photo gallery, metadata sections, external links, lightbox markup + JS |
| `templates/_results_partial.html` | Wrap `.set-card__name` in `<a href="/sets/{{ s.id }}">` |
| `templates/base.html` | Move `syncBrickset()` JS function here so both list and details share it |
| `templates/index.html` | Remove the now-duplicate `syncBrickset()` from its scripts block |
| `static/style.css` | New `.details-*` rules, `.lightbox` overlay, `.set-card__name-link` hover; bump cache buster `?v=4` → `?v=5` |
| `locales/en.json`, `locales/de.json` | 17 new keys under `details.*` |
| `tests/test_details_route.py` | **New** — route smoke + action-bar visibility tests |

No new dependencies. No DB migration. No new MCP servers.

## Open Questions

None remaining. All decisions confirmed via brainstorming dialogue 2026-05-17.
