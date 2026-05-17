# Details View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a canonical read-only details page at `GET /sets/{id}` — full-page set view with prominent photos, all metadata, external links, and edit/delete/sync actions. Set names on the collection list become the link to the new page.

**Architecture:** New route in `main.py` computes Brickset + merlinssteine URLs and renders a new `templates/details.html`. Responsive two-column grid (photos left, metadata right above 768px; stacked below). Vanilla-JS lightbox on thumbnail click. `syncBrickset()` JS moves from `index.html` to `base.html` so both list and details share it. List-card name becomes a link wrapping the existing `.set-card__name` div.

**Tech Stack:** FastAPI 0.115, Starlette 0.46, Jinja2 3.1, vanilla JS (no library for lightbox), SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-05-17-details-view-design.md`

---

## Phase 0 — Foundation

### Task 1: Move `syncBrickset()` from `index.html` to `base.html`

`syncBrickset()` is currently defined inline in `templates/index.html`. Both list and details views need it, so it moves to `base.html` to avoid duplication. Pure code relocation — no behaviour change.

**Files:**
- Modify: `templates/index.html` (remove `syncBrickset` from `{% block scripts %}`)
- Modify: `templates/base.html` (add `syncBrickset` to the existing `<script>` block)

- [ ] **Step 1: Read both files first** to see exact current locations.

`templates/index.html` has `syncBrickset` at lines ~134-146 inside `{% block scripts %}`. `templates/base.html` has a `<script>` block starting at line 56 that runs `lucide.createIcons()` and defines the delete-modal handlers.

- [ ] **Step 2: Add `syncBrickset` to `base.html`**

In `templates/base.html`, find the existing `<script>` block (around line 56). It currently looks like:

```html
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script>
  lucide.createIcons();

  // Delete modal
  let _deleteId = null;
  function openDeleteModal(id, name) {
    ...
  }
  ...
</script>
```

Insert the `syncBrickset` function as the FIRST function inside the script block (right after `lucide.createIcons();` and before `// Delete modal`):

```javascript
  // Shared Brickset sync handler — used by list cards and details view
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

  // Delete modal
  ...
```

- [ ] **Step 3: Remove `syncBrickset` from `index.html`**

In `templates/index.html`, in the `{% block scripts %}` section, delete the entire `syncBrickset` function (lines 134-146 approximately, including the `// ── Existing Brickset sync handler ────` comment block above it). The IIFE-style live-search/filter block that follows must stay intact.

After the edit, `index.html`'s scripts block should start directly with the `// ── Live search + filter ──────────` comment and the IIFE.

- [ ] **Step 4: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 98 passed (no test changes).

- [ ] **Step 5: Smoke test — sync button still works on the list page**

Start a temp uvicorn on port 8129 (background):
```
.venv/bin/uvicorn main:app --port 8129
```

Then verify `syncBrickset` is rendered into both `/` AND a sample edit page (which extends base.html):
```
curl -s http://localhost:8129/ | grep -c 'async function syncBrickset'
curl -s http://localhost:8129/sets/1/edit | grep -c 'async function syncBrickset'
```

Expect: each command prints `1`. (After the move, `syncBrickset` should appear once on each page — from `base.html`. If `/` shows 0 or 2, the move was incomplete.)

Kill: `pkill -f "port 8129"`.

- [ ] **Step 6: Commit**

```
git add templates/base.html templates/index.html
git commit -m "$(cat <<'EOF'
refactor(ui): move syncBrickset from index.html to base.html

Both the list view (Iteration 1) and the upcoming details view
need this helper, so it moves to base.html for shared access.
Pure code relocation — no behaviour change.
EOF
)"
```

---

## Phase 1 — Route + minimal page

### Task 2: `GET /sets/{id}` route + minimal `details.html` stub

TDD: define the route's behaviour with tests first (200 with content / 303 on missing id), implement the route returning a near-empty template, then expand the template in subsequent tasks.

**Files:**
- Modify: `main.py` (add new route)
- Create: `templates/details.html` (minimal stub)
- Create: `tests/test_details_route.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_details_route.py`:
```python
"""GET /sets/{id} — details view route."""
from fastapi.testclient import TestClient
from main import app
from tests.factories import make_set


def test_details_page_renders_existing_set(db):
    set_id = make_set(brand="LEGO", set_number="42171", name="McLaren P1", part_count=3893)
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The page must surface the set's identity
    assert "McLaren P1" in r.text
    assert "42171" in r.text
    assert "LEGO" in r.text


def test_details_page_redirects_for_missing_id(db):
    client = TestClient(app)
    r = client.get("/sets/9999", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/"
```

- [ ] **Step 2: Run, confirm failure**

Run: `.venv/bin/pytest tests/test_details_route.py -v`
Expected: 404 on both tests (the route doesn't exist yet).

- [ ] **Step 3: Create the minimal `templates/details.html`**

Write `templates/details.html`:
```html
{% extends "base.html" %}
{% block title %}{{ set.name }} ({{ set.brand }} {{ set.set_number }}) · Brickset Tracker{% endblock %}
{% block header_title %}{{ set.name }}{% endblock %}

{% block content %}
<div class="details">
  <div class="details__kicker">{{ set.brand | upper }} · <span class="mono">{{ set.set_number }}</span></div>
  <h1 class="details__name">{{ set.name }}</h1>
</div>
{% endblock %}
```

This is the minimum needed for the tests to pass. Subsequent tasks (4-7) expand the body.

- [ ] **Step 4: Add the route to `main.py`**

In `main.py`, find the existing `edit_page` route (the `@app.get("/sets/{set_id}/edit", ...)` block). Insert the NEW details route just BEFORE it (so `/sets/{id}` matches first; FastAPI tries routes in registration order):

```python
@app.get("/sets/{set_id}", response_class=HTMLResponse)
async def details_page(request: Request, set_id: int):
    s = get_set(set_id)
    if not s:
        return RedirectResponse("/", status_code=303)

    from execution.scraper import brand_to_slug
    brickset_url = (
        f"https://brickset.com/sets/{s['set_number']}-1/"
        if s.get("brickset_set_id") is not None else None
    )
    merlinssteine_url = (
        f"https://www.merlinssteine.de/sets/"
        f"{brand_to_slug(s['brand'])}-{s['set_number'].lower()}/"
    )

    return templates.TemplateResponse(request, "details.html", context=_ctx(
        request, set=s,
        brickset_url=brickset_url,
        merlinssteine_url=merlinssteine_url,
    ))
```

`get_set` and `RedirectResponse` are already imported. `brand_to_slug` is imported lazily inside the function (matches the existing lazy-import pattern in `api_save_set`).

- [ ] **Step 5: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_details_route.py -v`
Expected: 2 passed.

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 100 passed (98 prior + 2 new).

- [ ] **Step 6: Commit**

```
git add main.py templates/details.html tests/test_details_route.py
git commit -m "$(cat <<'EOF'
feat(routes): add GET /sets/{id} details page stub

Route computes Brickset + merlinssteine URLs from the set record
and renders a minimal template. Subsequent tasks expand the
template body (action bar, photos, metadata, lightbox).
EOF
)"
```

---

## Phase 2 — List card link

### Task 3: Wrap `.set-card__name` in `<a href="/sets/{id}">`

**Files:**
- Modify: `templates/_results_partial.html` (line ~52)

- [ ] **Step 1: Edit `_results_partial.html`**

Find this line:
```html
        <div class="set-card__name" title="{{ s.name }}">{{ s.name }}</div>
```

Replace with:
```html
        <a href="/sets/{{ s.id }}" class="set-card__name-link" title="{{ s.name }}">
          <div class="set-card__name">{{ s.name }}</div>
        </a>
```

The wrapping `<a>` is the link; the inner `<div>` keeps the existing typography styling.

- [ ] **Step 2: Verify tests still green**

Run: `.venv/bin/pytest -v`
Expected: 100 passed.

- [ ] **Step 3: Smoke test in browser**

Start uvicorn on port 8129 (background):
```
.venv/bin/uvicorn main:app --port 8129
```

Then:
```
curl -s http://localhost:8129/ | grep "set-card__name-link" | head -3
```
Expect at least one hit per existing set on the list (i.e., the test DB might be empty in this command's context if you run with no rows, but the production DB at `data/brickset.db` has 35 rows).

Optionally, click any set name in a browser at `http://localhost:8129/` — should navigate to `/sets/{id}` (renders the minimal page from Task 2; full content arrives in Tasks 4-7).

Kill: `pkill -f "port 8129"`.

- [ ] **Step 4: Commit**

```
git add templates/_results_partial.html
git commit -m "$(cat <<'EOF'
feat(ui): make set names on list cards link to /sets/{id}

Wraps .set-card__name in an <a> that navigates to the new details
page. Inner div preserves existing typography; CSS hover affordance
added in Task 9.
EOF
)"
```

---

## Phase 3 — Build out the details page

### Task 4: Header + action bar in `details.html`

Replace the minimal stub from Task 2 with the action bar + page header (kicker, name, status/condition tags).

**Files:**
- Modify: `templates/details.html`

- [ ] **Step 1: Overwrite `templates/details.html`**

Replace the file's contents with:

```html
{% extends "base.html" %}
{% block title %}{{ set.name }} ({{ set.brand }} {{ set.set_number }}) · Brickset Tracker{% endblock %}
{% block header_title %}{{ set.name }}{% endblock %}

{% block content %}

{# ── Action bar ───────────────────────────────────────────────────── #}
<div class="details-actionbar">
  <a href="/" class="btn btn-ghost">
    <i data-lucide="arrow-left" style="width:15px;height:15px"></i>
    {{ t('details.back') }}
  </a>
  <span class="spacer"></span>
  <a href="/sets/{{ set.id }}/edit" class="btn btn-secondary">
    <i data-lucide="pencil" style="width:15px;height:15px"></i>
    {{ t('edit.title') }}
  </a>
  <button class="btn btn-ghost"
          onclick="openDeleteModal({{ set.id }}, '{{ set.name | replace("'", "\\'") }}')">
    <i data-lucide="trash-2" style="width:15px;height:15px"></i>
  </button>
  {% if set.brickset_set_id is not none and set.brand | lower == 'lego' %}
  <button class="btn btn-ghost" title="{{ t('add.sync_brickset') }}"
          onclick="syncBrickset({{ set.id }}, this)">
    <i data-lucide="refresh-cw" style="width:15px;height:15px"></i>
  </button>
  {% endif %}
</div>

{# ── Page header ──────────────────────────────────────────────────── #}
{% set cond_class = {
  'ovp':      'cond-ovp',
  'im_bau':   'cond-im_bau',
  'gebaut':   'cond-gebaut',
  'abgebaut': 'cond-abgebaut',
  'verkauft': 'cond-verkauft',
} %}

<div class="details-header">
  <div class="details-header__left">
    <div class="details-header__kicker">{{ set.brand | upper }} · <span class="mono">{{ set.set_number }}</span></div>
    <h1 class="details-header__name">{{ set.name }}</h1>
  </div>
  <div class="details-header__tags">
    {% if set.status == 'draft' %}
      <span class="draft-badge">{{ t('list.draft_badge') }}</span>
    {% endif %}
    {% if set.condition %}
      <span class="condition-tag {{ cond_class.get(set.condition, '') }}">
        {{ t('condition.' ~ set.condition) }}
      </span>
    {% endif %}
  </div>
</div>

{# Tasks 5-7 add photo gallery, metadata sections, lightbox below this point. #}

{% endblock %}
```

- [ ] **Step 2: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 100 passed (the Task 2 tests assert "McLaren P1", "42171", "LEGO" are present — all still satisfied by the new header).

- [ ] **Step 3: Smoke test in browser**

Restart uvicorn (port 8129) and visit `http://localhost:8129/sets/1` (or whichever set id exists in your test DB). Verify:
- Action bar visible at top with Back / Edit / Delete / Sync buttons
- Kicker shows brand · set_number
- Set name visible as h1
- Status/condition tags appear when set (some test rows may not have them)

(Visual styling for `.details-actionbar`/`.details-header` arrives in Task 9 — for now the layout will look raw.)

- [ ] **Step 4: Commit**

```
git add templates/details.html
git commit -m "$(cat <<'EOF'
feat(details): add action bar + page header

Action bar with Back / Edit / Delete / Sync buttons. Sync rendered
only for LEGO sets with a brickset_set_id. Header has brand+number
kicker, name as h1, and the draft + condition tags right-aligned.
EOF
)"
```

---

### Task 5: Photo gallery in `details.html`

**Files:**
- Modify: `templates/details.html` (append a `.details-grid` wrapping a `.details-photos` column)

- [ ] **Step 1: Append the photo gallery block to `details.html`**

Find the placeholder comment `{# Tasks 5-7 add photo gallery, metadata sections, lightbox below this point. #}` and replace it with:

```html
{# ── Body grid: photos left, metadata right ───────────────────────── #}
<div class="details-grid">

  {# ── Photo gallery (left column on desktop) ────────────────────── #}
  <div class="details-photos">
    {% set has_own = set.own_photos and set.own_photos | length > 0 %}
    {% set has_web = set.web_images and set.web_images | length > 0 %}

    {% if has_own %}
      {% set main = '/' ~ set.own_photos[0] %}
    {% elif has_web %}
      {% set main = '/api/proxy-image?url=' ~ (set.web_images[0] | urlencode) %}
    {% else %}
      {% set main = '' %}
    {% endif %}

    <div class="details-photo-main" onclick="openLightbox(this.querySelector('img'))">
      {% if main %}
        <img src="{{ main }}" alt="{{ set.name }}">
      {% else %}
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="20" cy="21" r="6"/><circle cx="36" cy="21" r="6"/>
          <rect x="10" y="27" width="36" height="16" rx="3"/>
        </svg>
      {% endif %}
    </div>

    {% if has_own %}
    <div class="details-photo-thumbs" data-photo-group="own">
      {% for photo_path in set.own_photos %}
      <div class="details-photo-thumb" onclick="openLightbox(this.querySelector('img'))">
        <img src="/{{ photo_path }}" alt="">
      </div>
      {% endfor %}
    </div>
    {% endif %}

    {% if has_web %}
    <div class="details-photo-divider">{{ t('details.web_images_label') }}</div>
    <div class="details-photo-thumbs" data-photo-group="web">
      {% for url in set.web_images %}
      <div class="details-photo-thumb" onclick="openLightbox(this.querySelector('img'))">
        <img src="/api/proxy-image?url={{ url | urlencode }}" alt="">
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>

  {# ── Metadata column added in Task 6 ──────────────────────────── #}

</div>{# /details-grid #}
```

The `onclick="openLightbox(this.querySelector('img'))"` calls are placeholders that wire up to the lightbox JS in Task 7. The function won't exist yet — clicking will throw a JS console error until Task 7 lands. That's intentional and harmless for now.

- [ ] **Step 2: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 100 passed.

- [ ] **Step 3: Smoke test**

Reload `http://localhost:8129/sets/{id}` for a set that has photos (e.g. one of the imported LEGO sets from Iteration 3.5 — `s.web_images` should be populated). Verify:
- Main photo renders at full column width
- Thumbnail strip appears below (if more than one photo exists)
- "Web images" divider appears when both own + web exist
- For a set with no photos, the SVG brick placeholder renders

- [ ] **Step 4: Commit**

```
git add templates/details.html
git commit -m "$(cat <<'EOF'
feat(details): add photo gallery (main image + thumbnail strip)

Main image is the first own_photo (preferred) or first web_image,
falling back to the SVG brick placeholder. Thumbnails below: own
photos in one strip, then a divider, then web images. All thumbnails
wire up to openLightbox() — JS function arrives in Task 7.
EOF
)"
```

---

### Task 6: Metadata sections (Numbers, Where & how, External links)

**Files:**
- Modify: `templates/details.html` (add a `.details-meta` column inside `.details-grid`, after `.details-photos`)

- [ ] **Step 1: Insert the metadata column**

Find the comment `{# ── Metadata column added in Task 6 ──────────────────────────── #}` inside `.details-grid` and replace it with:

```html
  {# ── Metadata column (right column on desktop) ────────────────── #}
  <div class="details-meta">

    {# Section: Numbers — rendered only if at least one field present #}
    {% if set.part_count or set.minifigs or set.release_year or set.date_of_purchase or set.price_paid is not none or set.list_price is not none or set.ean %}
    <div class="details-meta__section">
      <h2 class="details-meta__heading">{{ t('details.section_numbers') }}</h2>
      <dl class="details-meta__list">
        {% if set.part_count %}
          <dt>{{ t('details.field_parts') }}</dt>
          <dd>{{ "{:,}".format(set.part_count).replace(",", ".") }}</dd>
        {% endif %}
        {% if set.minifigs %}
          <dt>{{ t('details.field_minifigs') }}</dt>
          <dd>{{ set.minifigs }}</dd>
        {% endif %}
        {% if set.release_year %}
          <dt>{{ t('details.field_released') }}</dt>
          <dd>{{ set.release_year }}</dd>
        {% endif %}
        {% if set.date_of_purchase %}
          <dt>{{ t('details.field_purchased') }}</dt>
          <dd class="mono">{{ set.date_of_purchase }}</dd>
        {% endif %}
        {% if set.price_paid is not none %}
          <dt>{{ t('details.field_price_paid') }}</dt>
          <dd>{{ "%.2f"|format(set.price_paid) }} €</dd>
        {% endif %}
        {% if set.list_price is not none %}
          <dt>{{ t('details.field_list_price') }}</dt>
          <dd>{{ "%.2f"|format(set.list_price) }} €</dd>
        {% endif %}
        {% if set.ean %}
          <dt>{{ t('details.field_ean') }}</dt>
          <dd class="mono">{{ set.ean }}</dd>
        {% endif %}
      </dl>
    </div>
    {% endif %}

    {# Section: Where & how #}
    {% if set.location or set.theme or set.note %}
    <div class="details-meta__section">
      <h2 class="details-meta__heading">{{ t('details.section_where') }}</h2>
      <dl class="details-meta__list">
        {% if set.location %}
          <dt>{{ t('details.field_location') }}</dt>
          <dd>{{ set.location }}</dd>
        {% endif %}
        {% if set.theme %}
          <dt>{{ t('details.field_theme') }}</dt>
          <dd>{{ set.theme }}</dd>
        {% endif %}
        {% if set.note %}
          <dt>{{ t('details.field_note') }}</dt>
          <dd style="white-space:pre-wrap">{{ set.note }}</dd>
        {% endif %}
      </dl>
    </div>
    {% endif %}

    {# Section: External links — merlinssteine always, Brickset conditional #}
    <div class="details-meta__section">
      <h2 class="details-meta__heading">{{ t('details.section_external') }}</h2>
      <ul class="details-meta__links">
        {% if brickset_url %}
        <li>
          <a href="{{ brickset_url }}" target="_blank" rel="noopener">
            <i data-lucide="external-link" style="width:13px;height:13px"></i>
            {{ t('details.link_brickset') }}
          </a>
        </li>
        {% endif %}
        <li>
          <a href="{{ merlinssteine_url }}" target="_blank" rel="noopener">
            <i data-lucide="external-link" style="width:13px;height:13px"></i>
            {{ t('details.link_merlinssteine') }}
          </a>
        </li>
      </ul>
    </div>

  </div>{# /details-meta #}
```

- [ ] **Step 2: Add an additional route test asserting external-link behaviour**

Append to `tests/test_details_route.py`:
```python
def test_details_page_renders_merlinssteine_link_always(db):
    """merlinssteine link is rendered for any brand, even when Brickset isn't applicable."""
    set_id = make_set(brand="BlueBrixx", set_number="103756", name="Castle", part_count=500)
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert "merlinssteine.de/sets/bb-103756" in r.text


def test_details_page_renders_brickset_link_only_when_id_set(db):
    """No brickset_set_id → no Brickset link."""
    set_id = make_set(brand="LEGO", set_number="00000", name="Unknown", part_count=1)
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert "brickset.com/sets/" not in r.text


def test_details_page_renders_brickset_link_when_id_set(db):
    """brickset_set_id present → Brickset link rendered."""
    from execution.db import get_connection
    set_id = make_set(brand="LEGO", set_number="42171", name="McLaren P1", part_count=3893)
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=48541 WHERE id=?", (set_id,))
    client = TestClient(app)
    r = client.get(f"/sets/{set_id}")
    assert "brickset.com/sets/42171-1/" in r.text


def test_details_page_renders_sync_button_only_for_lego_with_brickset_id(db):
    """Sync button visibility: LEGO + brickset_set_id."""
    from execution.db import get_connection
    # Case A: BlueBrixx with brickset_set_id (impossible in practice but test the guard)
    bx_id = make_set(brand="BlueBrixx", set_number="1", name="X", part_count=1)
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=1 WHERE id=?", (bx_id,))
    # Case B: LEGO without brickset_set_id
    lg_id = make_set(brand="LEGO", set_number="2", name="Y", part_count=1)
    # Case C: LEGO with brickset_set_id
    lg2_id = make_set(brand="LEGO", set_number="3", name="Z", part_count=1)
    with get_connection() as conn:
        conn.execute("UPDATE sets SET brickset_set_id=42 WHERE id=?", (lg2_id,))

    client = TestClient(app)
    # Case A: BlueBrixx + bs_id — sync NOT rendered (wrong brand)
    assert "syncBrickset(" + str(bx_id) + "," not in client.get(f"/sets/{bx_id}").text
    # Case B: LEGO without bs_id — sync NOT rendered (no id)
    assert "syncBrickset(" + str(lg_id) + "," not in client.get(f"/sets/{lg_id}").text
    # Case C: LEGO + bs_id — sync IS rendered
    assert "syncBrickset(" + str(lg2_id) + "," in client.get(f"/sets/{lg2_id}").text
```

- [ ] **Step 3: Run, confirm pass**

Run: `.venv/bin/pytest tests/test_details_route.py -v`
Expected: 6 passed (2 prior + 4 new).

Full suite:
Run: `.venv/bin/pytest -v`
Expected: 104 passed (100 prior + 4 new).

- [ ] **Step 4: Commit**

```
git add templates/details.html tests/test_details_route.py
git commit -m "$(cat <<'EOF'
feat(details): add metadata sections (Numbers, Where & how, External)

Each section renders only if it has at least one non-empty field.
External links: merlinssteine always rendered (URL via brand_to_slug
+ set_number); Brickset rendered only when brickset_set_id is set.
EOF
)"
```

---

### Task 7: Lightbox JS

**Files:**
- Modify: `templates/details.html` (add `{% block scripts %}` at the end + lightbox markup before `{% endblock %}` of content)

- [ ] **Step 1: Add the lightbox overlay markup**

In `templates/details.html`, just BEFORE the final `{% endblock %}` of the `content` block, insert:

```html
{# ── Lightbox overlay (hidden by default) ─────────────────────────── #}
<div class="lightbox hidden" id="lightbox">
  <img id="lightbox-img" alt="">
</div>
```

- [ ] **Step 2: Add the lightbox JS at the end of the file**

After the `{% endblock %}` of the `content` block (i.e., as the last thing in the file), add:

```html
{% block scripts %}
<script>
// ── Lightbox ──────────────────────────────────────────────────────────────
(function () {
  const overlay = document.getElementById('lightbox');
  const overlayImg = document.getElementById('lightbox-img');
  if (!overlay || !overlayImg) return;

  // Active list of img elements the user can cycle through with arrow keys.
  // Set when the lightbox opens; cleared when it closes.
  let activeImages = [];
  let activeIndex = -1;

  window.openLightbox = function (imgEl) {
    if (!imgEl) return;
    // Find the group: all images in the same .details-photo-thumbs group,
    // or all images in .details-photos if the main image was clicked.
    const group = imgEl.closest('.details-photo-thumbs')
      || imgEl.closest('.details-photo-main');
    activeImages = group ? Array.from(group.querySelectorAll('img')) : [imgEl];
    activeIndex = Math.max(0, activeImages.indexOf(imgEl));
    overlayImg.src = imgEl.src;
    overlay.classList.remove('hidden');
  };

  function closeLightbox() {
    overlay.classList.add('hidden');
    overlayImg.src = '';
    activeImages = [];
    activeIndex = -1;
  }

  function step(delta) {
    if (activeImages.length < 2) return;
    activeIndex = (activeIndex + delta + activeImages.length) % activeImages.length;
    overlayImg.src = activeImages[activeIndex].src;
  }

  overlay.addEventListener('click', closeLightbox);
  document.addEventListener('keydown', (e) => {
    if (overlay.classList.contains('hidden')) return;
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowLeft')  step(-1);
    else if (e.key === 'ArrowRight') step(1);
  });
})();
</script>
{% endblock %}
```

Notes:
- The `window.openLightbox = function (...)` assignment exposes the function globally so the inline `onclick` handlers in Task 5's markup can reach it.
- The "group detection" uses `imgEl.closest('.details-photo-thumbs')` to find the strip the image belongs to. The main image is in `.details-photo-main` instead; clicking it shows just that single image in the lightbox (no arrow navigation, since `activeImages.length < 2`). That's a reasonable trade-off — if you want main-image arrow nav across all photos in the set, the `step()` guard prevents weirdness.

- [ ] **Step 3: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 104 passed.

- [ ] **Step 4: Smoke test in browser**

Reload a details page that has multiple photos. Click any thumbnail:
- Fullscreen overlay opens
- Image visible
- Click backdrop → closes
- Open again, press Esc → closes
- Open again, press ← / → → cycles through thumbnails in that strip
- Click main image → opens with just that one image (no nav)

- [ ] **Step 5: Commit**

```
git add templates/details.html
git commit -m "$(cat <<'EOF'
feat(details): add vanilla-JS lightbox

Click any thumbnail or main image → fullscreen overlay. Click
backdrop or press Esc → close. Arrow keys cycle within the active
photo strip (own or web). No library; ~30 lines of inline JS.
EOF
)"
```

---

## Phase 4 — Polish

### Task 8: Add 17 i18n keys

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/de.json`

- [ ] **Step 1: Add new `"details"` block to `locales/en.json`**

Add a new top-level `"details"` object (place it between `"list"` and `"import"`, or wherever makes alphabetical sense, preserving comma rules):

```json
  "details": {
    "back":                 "← Back to collection",
    "section_numbers":      "Numbers",
    "section_where":        "Where & how",
    "section_external":     "External links",
    "web_images_label":     "Web images",
    "field_parts":          "Parts:",
    "field_minifigs":       "Minifigs:",
    "field_released":       "Released:",
    "field_purchased":      "Purchased:",
    "field_price_paid":     "Price paid:",
    "field_list_price":     "List price:",
    "field_ean":            "EAN:",
    "field_location":       "Location:",
    "field_theme":          "Theme:",
    "field_note":           "Note:",
    "link_brickset":        "Brickset page",
    "link_merlinssteine":   "merlinssteine.de page"
  },
```

JSON comma discipline: the previous block must end with a `,`; the `"details"` block ends with a `,` because more blocks follow.

- [ ] **Step 2: Add the same block to `locales/de.json`** with German values

```json
  "details": {
    "back":                 "← Zurück zur Sammlung",
    "section_numbers":      "Zahlen",
    "section_where":        "Wo & wie",
    "section_external":     "Externe Links",
    "web_images_label":     "Web-Bilder",
    "field_parts":          "Teile:",
    "field_minifigs":       "Minifiguren:",
    "field_released":       "Erschienen:",
    "field_purchased":      "Gekauft:",
    "field_price_paid":     "Kaufpreis:",
    "field_list_price":     "Listenpreis:",
    "field_ean":            "EAN:",
    "field_location":       "Standort:",
    "field_theme":          "Thema:",
    "field_note":           "Notiz:",
    "link_brickset":        "Brickset-Seite",
    "link_merlinssteine":   "merlinssteine.de-Seite"
  },
```

- [ ] **Step 3: Validate JSON parity**

Run:
```
.venv/bin/python -c "
import json
en = json.load(open('locales/en.json'))
de = json.load(open('locales/de.json'))
assert set(en['details'].keys()) == set(de['details'].keys())
assert len(en['details']) == 17
print('OK', len(en['details']))
"
```
Expected: `OK 17`.

- [ ] **Step 4: Smoke check translations render**

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
    set_id = make_set(brand='LEGO', set_number='42171', name='McLaren P1', part_count=3893, list_price=449.99)
    with TestClient(app) as client:
        de = client.get(f'/sets/{set_id}', cookies={'lang': 'de'}).text
        en = client.get(f'/sets/{set_id}', cookies={'lang': 'en'}).text
        for needle in ['Zurück zur Sammlung', 'Zahlen', 'Externe Links', 'Listenpreis:']:
            assert needle in de, f'DE missing {needle}'
        for needle in ['Back to collection', 'Numbers', 'External links', 'List price:']:
            assert needle in en, f'EN missing {needle}'
        print('OK')
"
```
Expected: `OK`.

- [ ] **Step 5: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 104 passed.

- [ ] **Step 6: Commit**

```
git add locales/en.json locales/de.json
git commit -m "$(cat <<'EOF'
feat(i18n): add details view translation keys

17 new keys under details.* covering back link, section headers,
field labels, and external link labels. EN and DE in parity.
EOF
)"
```

---

### Task 9: CSS for details page + cache buster bump

**Files:**
- Modify: `static/style.css` (append new rules)
- Modify: `templates/base.html` (bump `?v=4` → `?v=5`)

- [ ] **Step 1: Bump cache buster in `templates/base.html`**

Find the line `<link rel="stylesheet" href="/static/style.css?v=4">` (line 8) and change to `?v=5`.

- [ ] **Step 2: Append CSS to `static/style.css`**

Append at the end of `static/style.css`:

```css
/* ---------- Set-Name Link on List Cards --------------------------- */
.set-card__name-link {
  color: inherit;
  text-decoration: none;
  display: block;
}
.set-card__name-link:hover .set-card__name {
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  color: var(--accent);
}

/* ---------- Details Page ------------------------------------------ */
.details-actionbar {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-4);
  padding-bottom: var(--sp-3);
  border-bottom: 1px solid var(--rule);
}
.details-actionbar .spacer { flex: 1; }

.details-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-4);
  margin-bottom: var(--sp-5);
}
.details-header__left { min-width: 0; flex: 1; }
.details-header__kicker {
  font: 500 11px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--sp-2);
}
.details-header__name {
  font-family: var(--font-display);
  font-style: italic;
  font-weight: 400;
  font-size: 28px;
  line-height: 1.15;
  color: var(--fg-heading);
}
.details-header__tags {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  align-items: flex-end;
  flex-shrink: 0;
}

.details-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--sp-5);
}
@media (min-width: 768px) {
  .details-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }
}

.details-photos {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.details-photo-main {
  width: 100%;
  aspect-ratio: 1 / 1;
  background: var(--bg-card);
  border: 1px solid var(--rule);
  border-radius: var(--r-md);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--rule-strong);
  cursor: zoom-in;
}
.details-photo-main img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--weiss);
}
.details-photo-main svg { width: 64px; height: 64px; }

.details-photo-thumbs {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}
.details-photo-thumb {
  width: 80px;
  height: 80px;
  border-radius: var(--r-sm);
  overflow: hidden;
  border: 1px solid var(--rule);
  background: var(--weiss);
  cursor: zoom-in;
  transition: border-color var(--dur-fast) var(--ease-out);
}
.details-photo-thumb:hover { border-color: var(--kuestenblau); }
.details-photo-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.details-photo-divider {
  margin-top: var(--sp-3);
  font: 500 10px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  padding-bottom: var(--sp-1);
  border-bottom: 1px solid var(--rule);
}

.details-meta {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}
.details-meta__section { }
.details-meta__heading {
  font: 500 12px/1 var(--font-body);
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--sp-3);
  padding-bottom: var(--sp-2);
  border-bottom: 1px solid var(--rule);
}
.details-meta__list {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--sp-2) var(--sp-4);
  font-size: 14px;
}
.details-meta__list dt {
  font: 400 13px/1.4 var(--font-body);
  color: var(--fg-muted);
}
.details-meta__list dd {
  font: 400 14px/1.4 var(--font-body);
  color: var(--fg);
}
.details-meta__links {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.details-meta__links a {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font: 400 14px/1 var(--font-body);
  color: var(--accent);
  text-decoration: none;
}
.details-meta__links a:hover { text-decoration: underline; }

/* ---------- Lightbox ---------------------------------------------- */
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
  padding: var(--sp-5);
}
.lightbox img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  box-shadow: var(--shadow-floating);
}
```

- [ ] **Step 3: Verify pytest still green**

Run: `.venv/bin/pytest -v`
Expected: 104 passed.

- [ ] **Step 4: Smoke check that the stylesheet bump rendered**

```
cd /Users/hhalfpap/git/projects/own/brickset-tracker && .venv/bin/python -c "
from fastapi.testclient import TestClient
from main import app
r = TestClient(app).get('/')
assert 'style.css?v=5' in r.text, 'cache buster not bumped'
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```
git add static/style.css templates/base.html
git commit -m "$(cat <<'EOF'
style: add details page CSS + lightbox overlay + bump cache buster

Responsive two-column grid (single column below 768px). Photo
main + thumbnail strip layout, definition-list metadata blocks,
fullscreen lightbox overlay, set-name link hover affordance on
list cards. v=4 → v=5.
EOF
)"
```

---

### Task 10: Final end-to-end manual verification

**Files:** none modified.

Walk through these scenarios in the live server in both DE and EN.

- [ ] **Step 1: Restart server**

```
pkill -f "uvicorn main:app --port 8123" 2>/dev/null
.venv/bin/uvicorn main:app --port 8123 --reload
```
Run with `run_in_background: true`. Wait for `Application startup complete.`.

- [ ] **Step 2: Set-name link on list cards**

Visit `http://localhost:8123/`. Hover over any set name — it should show an underline + accent color. Click → navigates to `/sets/{id}`.

- [ ] **Step 3: Details page header**

Verify:
- Browser tab title: `{name} ({brand} {set_number}) · Brickset Tracker`
- Top action bar visible: Back / Edit / Delete / Sync (last only for LEGO with brickset_set_id)
- Kicker line shows `BRAND · set_number`
- Set name as h1
- Draft badge + condition tag right-aligned (only when present)

- [ ] **Step 4: Photo gallery**

For a set with photos:
- Main image at full column width
- Thumbnail strip below
- "Web images" / "Web-Bilder" divider if both own + web present
- Hover any thumbnail — border turns accent color
- Click any thumbnail → lightbox opens
- In lightbox: click backdrop → closes; Esc → closes; ← / → cycles through thumbs in that strip

For a set with no photos:
- SVG brick placeholder fills the main-image slot

- [ ] **Step 5: Metadata sections**

Verify the right column shows:
- "Numbers" section with whatever fields are populated (parts, minifigs, year, date, prices, EAN). Section header hidden when no fields populated.
- "Where & how" section with location/theme/note. Same conditional rendering.
- "External links" section: merlinssteine link always; Brickset link only for LEGO sets with brickset_set_id.

Click the Brickset link → opens in new tab on the real Brickset page.
Click the merlinssteine link → opens in new tab on the real merlinssteine page (or 404 if the set isn't there).

- [ ] **Step 6: Action bar actions**

- Click Edit → goes to `/sets/{id}/edit`
- Click Delete → confirmation modal opens; Cancel → modal closes; OK (after confirming) → set is deleted and redirects to `/`
- Click Sync (where shown) → button shows spinner, then check icon on success

- [ ] **Step 7: Responsive behavior**

Resize the browser window narrow (< 768px). The two-column grid should collapse to a single column: header → photos → metadata stacked vertically. Lightbox still works at any width.

- [ ] **Step 8: Language toggle**

Switch DE ↔ EN. All labels translate: "Back to collection" / "Zurück zur Sammlung", section headers, field labels, link labels.

- [ ] **Step 9: 404 redirect**

Visit `/sets/99999` (non-existent id). Browser redirects to `/`.

- [ ] **Step 10: Mark verification commit**

```
git commit --allow-empty -m "$(cat <<'EOF'
chore: verify details view end-to-end

All scenarios in plan Task 10 pass in both DE and EN. Set-name
link, action bar, photo gallery with lightbox, metadata sections,
external links, responsive layout, and 404 redirect all working.
EOF
)"
```

---

## Done

Iteration 4 complete. Set names on the collection list now navigate to a canonical per-set page with prominent photos, a lightbox for browsing, all metadata in tidy sections, and one-click access to edit/delete/sync plus the set's Brickset and merlinssteine.de pages.

Next on the V1 path: **Iteration 4.5 (brand-slug config — surfaced during Iteration 4 brainstorming) → code review → Phase T (LaunchAgent)**.
