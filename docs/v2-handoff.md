# V2 Handoff — brickset-tracker

> Compiled 2026-05-18, after V1.1c shipped. Primary reader: **future-me, 6–18 months from now**, returning to the project to pick the next thing to ship.
>
> Items are categorised (A–F) and tier-flagged (🔥 / 💡 / 🔭). Each item assumes familiarity with the V1 vocabulary (A.N.T. layers, B.L.A.S.T. phases, the "Verklemmt und zugenäht!" design system, and the iteration-spec/plan discipline under `docs/superpowers/`).

## How to use this doc

- 🔥 = **do this next** — well-understood, clear value, low risk
- 💡 = **nice to have** — clear value but not urgent, or some unknowns
- 🔭 = **speculative** — interesting direction, may not survive contact with V2 priorities

Each item: brief paragraph covering **what** it is, **why** it was deferred from V1, and a **sketch** of how to approach it.

## Quick start when picking this up again

1. **`./scripts/launchagent.sh status`** — is the server still running cleanly?
2. **`.venv/bin/python -m pytest -q`** — does the existing test suite (170 as of 2026-05-18) still pass?
3. **Skim `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md`** — what was the last completed iteration?
4. **Pick a 🔥 item from this doc** and run the standard cycle: brainstorm → spec → plan → execute via subagent-driven development.

---

## Category A — User-facing features

### A1. Import (reverse of CSV/JSON export) 🔥

**What:** Upload a JSON or CSV file produced by `/api/export/*` and recreate the sets. The natural complement to the V1.1c export and the cleanest path to migrate the collection to a new machine without copying `data/` manually.

**Why deferred:** V1.1c was already a two-feature bundle (clone + export). Adding import would have tripled scope. The user flagged it as a V2 must-have during the V1.1c spec review.

**Sketch:** New routes `POST /api/import/json` and `POST /api/import/csv`. Multipart upload of the file. Validation pass (schema match, required fields), then a preview screen (same UX as the Brickset import preview: "X new, Y already exist as duplicates"). Confirmation kicks off `save_set()` per row. Decide upfront: round-trip the file from `/api/export/json` should produce zero new rows on re-import (idempotent identity match via brand+set_number+brickset_set_id). The CSV middot-separator from V1.1c needs reverse handling — replace ` · ` with `\n` in note when importing.

### A2. Stats dashboard 💡

**What:** A `/stats` page summarising the collection: counts by theme/year/condition, total `price_paid` vs `list_price`, parts-owned aggregate, brand distribution, longest-owned set.

**Why deferred:** Wasn't blocking daily use. Surfaced in the B.L.A.S.T. discovery as "Later" in the iteration plan.

**Sketch:** Reuse `get_sets()` (no filters) → aggregate in Python → render with the existing chart-free table aesthetics. Maybe one or two bar widths via CSS variables; avoid a chart library. New route + template; no schema changes.

### A3. Card grid view 💡

**What:** A toggle on the collection list between the current row-style and a denser grid of cards (image-forward, less metadata visible). Useful when you want to scroll through visuals rather than dimensions.

**Why deferred:** Surfaced in the B.L.A.S.T. discovery as "Later". Row view does the job for now.

**Sketch:** Same `get_sets()` result, second template (`_grid_partial.html`). View preference stored in a cookie (like `lang`). The settings page (`/settings/brand-slugs`) could grow a section. Existing `_results_partial.html` becomes the row view; new `_grid_partial.html` is the alternative.

### A4. Keyboard shortcuts 💡

**What:** `/` to focus the search box on `/`, `g a` to navigate to `/add`, `Esc` to close any open modal/lightbox (Esc already closes the lightbox; extend to the delete-confirmation modal). Vim-style `j` / `k` to walk the list. Single-key shortcuts only when no input has focus.

**Why deferred:** Pure ergonomics; daily mouse-driven use covers the workflow today.

**Sketch:** One small global JS file under `static/` (first shared JS file in the project — currently every template ships its own inline JS). Wire shortcuts through a single `document.addEventListener('keydown', ...)` with focus-detection.

### A5. Native CSV import wizard 🔭

**What:** A friendlier alternative to "round-trip the export". User uploads any CSV (not necessarily ours), maps columns to our schema interactively, gets a preview before committing.

**Why deferred:** A4 (Import) covers the common case. This is V3+ territory unless someone surfaces a real need (e.g. migrating from a different tracker).

**Sketch:** Reuse the import-preview UI from A4. Add a column-mapping step before the preview: client-side JS reads the header row, server returns the list of importable fields, user wires them up.

---

## Category B — Operational hardening

### B1. Scripted backup to iCloud Drive 🔥

**What:** A daily `cp data/brickset.db ~/Library/Mobile\ Documents/com~apple~CloudDocs/brickset-tracker-backup/$(date +%Y-%m-%d).db` (plus a matching `rsync` of `uploads/`) running on a `StartCalendarInterval` LaunchAgent. Time Machine helps but a restore-from-scratch would force you to rebuild the DB; iCloud-resident snapshots survive everything.

**Why deferred:** The "decide during code review" list from 2026-05-16. V1 ships without it; user accepts the risk for now.

**Sketch:** A second LaunchAgent plist at `scripts/de.hhalfpap.brickset-tracker-backup.plist.template` + a `backup.sh` companion to `launchagent.sh`. Daily at e.g. 03:00. Rotate: keep last 30 days, weekly thereafter. Output to a single iCloud Drive folder so the Files.app on iPhone/iPad can see the same snapshots.

### B2. Log rotation for `~/Library/Logs/brickset-tracker.log` 💡

**What:** The current LaunchAgent writes both stdout and stderr to one file, unbounded. After 18 months of daily uvicorn restarts + requests, this file will be sizeable.

**Why deferred:** Phase T spec explicitly punted log rotation as out-of-scope.

**Sketch:** macOS `newsyslog.d` config under `/etc/newsyslog.d/brickset-tracker.conf` rotates the file weekly (or at 10 MB), keeps 4 generations, gzips. One config file, one `sudo` install step. Document in `scripts/README.md`.

### B3. Confirm `BRICKSET_DATA_DIR` works end-to-end with the LaunchAgent 💡

**What:** V1.1b added `BRICKSET_DATA_DIR` so the DB+uploads can live outside the project tree (e.g. `~/Library/Application Support/brickset-tracker/`). Tests prove the modules read the env var. The LaunchAgent plist doesn't yet pass it through — `EnvironmentVariables` in the plist template only sets `PATH`.

**Why deferred:** Unsexy. The default (env var unset, data in `./data` and `./uploads`) works fine and is what's currently running.

**Sketch:** Decide a canonical location (e.g. `~/Library/Application Support/brickset-tracker/`). Add `BRICKSET_DATA_DIR` to `scripts/de.hhalfpap.brickset-tracker.plist.template`'s `EnvironmentVariables` dict, sourced from `.env`. The install script reads `.env`, threads the value through the `sed` substitutions, and migrates existing data on first install (`mv data uploads "$BRICKSET_DATA_DIR/"` with a backup).

---

## Category C — Code-quality debt

### C1. Promote `_find_duplicates` to `find_duplicates` 💡

**What:** The function in `navigation/set_manager.py` is prefixed with `_` (module-private), but `navigation/lookup_router.py` imports it from outside the module (added in Iteration 4.6 S3). The underscore is now misleading.

**Why deferred:** Tagged as a V1.5 cleanup during the Iteration 4.6 final review.

**Sketch:** Rename, update the import in `lookup_router.py`, search for any other callers (`grep -rn _find_duplicates`). Pure-mechanical, but touches multiple files — easy review.

### C2. i18n-aware callout labels 💡

**What:** The `showCallout(msg, type)` function in `templates/add.html` and `templates/edit.html` uses a hardcoded `typeMap = { warn: 'Achtung', info: 'Hinweis', error: 'Fehler', ok: 'Klappt' }`. These should come from `t('callout.warn')` etc.

**Why deferred:** Pre-existing in `add.html`; mirrored to `edit.html` during Iteration 4.6 S5 for consistency. Flagged as a V1.5 cleanup at that time.

**Sketch:** Add 4 keys per locale (`callout.warn`, `callout.info`, `callout.error`, `callout.ok`). Replace the `typeMap` object with template-injected values (the same `__N__` trick used elsewhere for runtime placeholders). When the user switches language, the page re-renders anyway, so static template injection is enough.

### C3. `relative_to(Path("."))` brittleness in `execution/photos.py` 💡

**What:** `upload_to_staging` and `finalise_photos` compute return-value paths via `dest.relative_to(Path("."))`. This throws `ValueError` when `dest` is an absolute path outside cwd — which happens whenever a test monkeypatches `STAGING_ROOT` to an absolute `tmp_path`.

**Why deferred:** The F5 test fix in Iteration 4.6 worked around it via `chdir(tmp_path)`. Production code is unaffected (the LaunchAgent's WorkingDirectory matches the assumption).

**Sketch:** Replace with `os.path.relpath(dest, start=PROJECT_ROOT)` or similar, where `PROJECT_ROOT` is a stable absolute anchor. Then F5's happy-path test could use the natural `monkeypatch.setattr(STAGING_ROOT, ...)` approach instead of `chdir`. Touches `execution/photos.py` + 1 test simplification.

### C4. Composite index on `(brand, set_number)` 💡

**What:** `find_local_rows_missing_brickset_id` filters by `brand=? AND set_number=? AND brickset_set_id IS NULL`. The existing `idx_sets_brand` only covers `brand`; the engine still scans within the brand to filter set_number.

**Why deferred:** Performance is fine at 38 sets. Wouldn't matter until the collection grows to several hundred.

**Sketch:** `CREATE INDEX IF NOT EXISTS idx_sets_brand_set_number ON sets(brand, set_number);` in `execution/db.py:init_db()`. Idempotent. Zero risk.

### C5. Per-row DB batching in import-commit 💡

**What:** `api_import_commit` calls `find_local_rows_missing_brickset_id` once per row in the loop. For a 200-set Brickset import, that's 200 indexed queries (~few ms each).

**Why deferred:** Acceptable at current scale; explicitly accepted as a trade-off during the Iteration 4.6 F2 fix.

**Sketch:** Replace the per-row call with one batched query: `SELECT id, brand, set_number FROM sets WHERE (brand, set_number) IN (...) AND brickset_set_id IS NULL`. Group results by `(brand, set_number)` in Python and pass the right slice to each row.

---

## Category D — Test backfill

(All items: pre-existing pre-Iteration-3 code that has no direct unit tests. The framework exists; just need to backfill.)

### D1. `execution/scraper.py` 💡

**What:** Direct tests for `_brand_slug()` and the full scrape happy path with a captured HTML fixture from `merlinssteine.de`.

**Why deferred:** `_parse_price` already has a test (`test_scraper_list_price.py`). Other functions are exercised indirectly via route tests.

**Sketch:** One HTML fixture file under `tests/fixtures/scraper/`, parametrise across a few brand+slug examples. Mock `httpx.AsyncClient` returning the fixture bytes.

### D2. `save_set()` happy paths 💡

**What:** Round-trip tests for: complete record (all required fields present, status='complete'), draft record (missing required, status='draft'), duplicate-detection (returns the existing rows list).

**Why deferred:** Lightly covered indirectly via the route tests. Direct tests would lock in the contract.

**Sketch:** Three pytest functions using `make_set` + a fresh `save_set()` call. Assert returned `{id, status, duplicates, missing}`.

### D3. `execution/photos.py` direct tests 💡

**What:** Direct tests for `upload_to_staging` (size limits, file-type rejection), `finalise_photos`, `cleanup_stale_staging`. Currently only exercised through the F5 + S2 tests added in Iteration 4.6 (which test the routes, not the helpers).

**Why deferred:** Indirect coverage is mostly sufficient.

**Sketch:** New `tests/test_photos.py`. Parametrise across edge cases (`.heic` allowed, `.exe` rejected, 25 MB file rejected, etc.).

### D4. `execution/i18n.py` direct tests 💡

**What:** Direct tests for `t()`: key lookup, fallback to the key when missing, placeholder substitution (`t('errors.duplicate_warning', count=2)`).

**Why deferred:** Tested indirectly through every template rendering test.

**Sketch:** Three small tests. The fallback case is the most valuable to lock down — easy to break silently if we ever refactor.

### D5. `navigation/lookup_router.py` 💡

**What:** EAN routing across all four paths: cache hit, cache miss → scrape success, unresolved → manual fallback, ambiguous (multiple matches).

**Why deferred:** The S3 test in Iteration 4.6 covers the happy path. Other branches are speculatively-tested at best.

**Sketch:** Four tests, each mocking a different combination of `resolve_ean`, `scrape_set`, `fetch_set` return values.

### D6. `main.py` route smoke tests 💡

**What:** Smoke tests for: `/set-lang` (cookie set, redirect), `/api/sets` GET (full collection, used by tests already), `/api/sets/{id}/update` happy path, full edit round-trip via the API.

**Why deferred:** Many routes have indirect coverage. Direct smoke tests would catch regressions in route shape.

**Sketch:** Existing test files have the pattern. Add ~6 new tests in `tests/test_route_smoke.py`.

---

## Category E — Advanced features (speculative)

### E1. Multi-user / LAN access 🔭

**What:** Currently the server binds to `127.0.0.1`. If you ever want to browse the collection from your phone on the same network: switch to `0.0.0.0` + a token-based auth layer.

**Why deferred:** Personal-machine-only is the explicit design contract. Don't break it lightly.

**Sketch:** Single auth token in `.env` (`BRICKSET_TRACKER_TOKEN`). FastAPI middleware checks `?token=...` query param or `Authorization: Bearer` header. Frontend on the LAN includes the token in a cookie set once. Tedious to retrofit; consider whether you really want this before starting.

### E2. Brickset two-way sync 🔭

**What:** Currently we only pull from Brickset. Push direction: when a local set has a `brickset_set_id` but the Brickset collection doesn't reflect ownership, mark it owned via the API. Rare but possible for MOC reuse + manual `brickset_set_id` entry.

**Why deferred:** The pull-only model covers daily use. Pushing requires more careful auth + error handling around the Brickset API.

**Sketch:** New `execution/brickset.py:push_owned()` helper. Settings page exposes a "Sync ownership to Brickset" button per set. Idempotent (Brickset accepts the same `qtyOwned` repeatedly).

### E3. Image hashing for search across own photos 🔭

**What:** Drop a photo into the app, find sets in the collection where you have a similar own photo. Useful only at large collection scale (hundreds of sets, multiple own photos each).

**Why deferred:** Adds image-processing dependencies (`Pillow`, perhaps `imagehash`) and disk-space overhead. ROI unclear until the collection is much bigger.

**Sketch:** Background job computes pHash for each `own_photos[]` entry on save. Search route does pHash distance comparison. New table `photo_hashes (set_id, photo_path, phash, computed_at)`.

### E4. Tag system beyond `condition` 🔭

**What:** Free-form tags for "loaned to Anna", "Ebay candidate", "Christmas gift", etc. Multi-tag per set; filter the list by tag.

**Why deferred:** `condition` + `note` + `location` cover most cases. Tags would expand the schema and the UI.

**Sketch:** New table `tags (id, set_id, tag)` (or a JSON `tags TEXT` column on `sets`). Tag suggestions from existing tags on the set form. Filter chip on the search/filter row.

---

## Category F — Adjacent projects

### F1. Publish the "Verklemmt und zugenäht!" design system 🔭

**What:** Extract `static/style.css` (currently coupled to brickset-tracker via class names like `.details-photo-main`) into a standalone repo. CSS custom properties (`--sp-*`, `--dur-*`, color tokens) are the system's contract; component examples are documentation.

**Why deferred:** Not a priority; the user mentioned "It's not a priority, it's just something I've been using internally."

**Sketch:** New repo `verklemmt-und-zugenaeht` (or similar slug). Three artifacts inside: `tokens.css` (custom properties only), `components.css` (button, callout, modal, lightbox, photo grids — strip brickset-specific class names), `index.html` (single demo page showing every component with example markup). Host the demo via GitHub Pages. Reference from brickset-tracker's README. See the inline pointer in this session's history for full sketch — about an evening of work.

---

## Closing note

Every shipped iteration has:

- A spec under `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- An implementation plan under `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`

Read those before designing a new iteration — many of the gotchas you'd otherwise rediscover were already documented:

- Why F3 needs `preview_local_qty` (Iteration 4.6 cluster A)
- Why we use `forceescape` (not `escape`) for JSON-in-HTML attributes (V1.1c hotfix `43f7ecf`)
- Why the LaunchAgent's smoke window is 15s, not 5s (Phase T `cf63f73`)
- Why `nc -l` doesn't work as a port blocker on macOS (Phase T Task 3 dispatch notes)
- Why CSV exports replace `\n` with ` · ` even though `QUOTE_ALL` is on (V1.1c hotfix `b058ddb`)
- Why the `tojson` filter alone wasn't enough to embed Brickset JSON in a `<script>` tag (Iteration 4.6 F1)

Also read **`CLAUDE.md`** at the repo root — that's the project constitution. Data schema, behavioural rules, the condition enum, language defaults, A.N.T. invariants. Changes to those are bigger decisions than feature work.

And finally — **`~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md`** is the running history of what shipped when. The B.L.A.S.T. checklist + Road to V1 (and V1.1) are all there. The post-V1.1 entries are where you'll add your own iteration markers.

Welcome back, future-me. Have fun.
