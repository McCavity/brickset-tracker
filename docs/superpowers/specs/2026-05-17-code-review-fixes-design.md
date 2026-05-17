# Code-Review Fixes — Design

**Status:** Approved 2026-05-17
**Project:** brickset-tracker
**Iteration:** 4.6
**Last V1 work before Phase T (LaunchAgent).**

## Goal

Address all "Fix-before-V1" (F1–F5) and "Fix-soon" (S1–S5) findings from the pre-V1 code review (three reviewers: Codex standard, Codex adversarial, superpowers code-reviewer). Each fix is small, but together they close the remaining correctness, safety, UX, and lifecycle gaps before V1 ships.

Out of scope: anything labelled "Defer" in the review synthesis, README/backup/export work, and anything not on the F/S list. No new user-facing features.

## Findings Addressed

### Cluster A — Brickset import safety (4 fixes)

The Brickset bulk-import flow added in Iteration 3.5 has three correctness gaps and one XSS hole. All four live close together in `main.py`, `navigation/set_manager.py`, `templates/_brickset_import_preview.html`, and `execution/brickset.py`.

#### F1 — Escape JSON embedded in the preview script tag

`templates/_brickset_import_preview.html:70` currently emits Brickset-supplied JSON with `| safe` inside a `<script>` block. A set name containing `</script>` would terminate the script element and allow injected HTML/JS into the import page.

**Change:**
- Template: replace `{{ row.payload_json | safe }}` with `{{ row.payload | tojson }}`. Jinja's `tojson` filter escapes `<`, `>`, `&`, `'` as `\u00XX` so a `</script>` substring in the data cannot terminate the surrounding `<script>` element.
- `main.py` import-preview handler: pass `payload` (the dict) instead of `payload_json` (the pre-serialised string) to the template.
- Delete the now-unused `json.dumps(...)` line that produced `payload_json`.

**Reason:** Defence in depth. Brickset is not malicious, but set names are arbitrary external strings and the preview lives inside a privileged app context.

#### F2 — Re-derive `local_ids_missing_bs_id` server-side on commit

The preview embeds `local_ids_missing_bs_id` (a list of local row ids) into the form, and the commit handler trusts the client-submitted value. A stale preview, a tampered payload, or a concurrent edit can cause `commit_import_rows` to attach a Brickset id to the wrong local row, permanently poisoning details links and Brickset sync counts.

**Change:**
- `main.py` import-commit handler: ignore the client-submitted `local_ids_missing_bs_id`. For each preview row, call `find_local_rows_missing_brickset_id(brand, set_number)` again right before invoking `commit_import_rows` and pass the freshly-derived list.
- `navigation/set_manager.py:commit_import_rows`: keep accepting the list as a parameter (no signature change), but the source of truth is now the server, not the form.

**Reason:** The persistence layer enforces the invariant by construction. No need to add `AND brand=? AND set_number=? AND brickset_set_id IS NULL` to the UPDATE — the server-derived list cannot include rows that violate that condition, because that's what `find_local_rows_missing_brickset_id` filters by.

#### F3 — Make import commit idempotent / retry-safe

`commit_import_rows` inserts `import_qty` rows exactly as submitted. A double-click, a refresh of a stale preview, or a slow network producing a retry inserts the same Brickset rows twice as complete collection records — which the next Brickset sync then mirrors back as inflated quantities.

**Change in `navigation/set_manager.py:commit_import_rows`:**

Inside the same DB transaction, before inserting:
1. Compute `current_local_count = count_owned(brand, set_number)` using the live connection.
2. Compute `actual_insert = max(0, import_qty - current_local_count)`.
3. Insert `actual_insert` rows instead of `import_qty`.

The semantic shift: the client-supplied `import_qty` becomes the **desired final state** (own this many copies of this set), not the **delta** (insert this many new rows). A re-submitted commit becomes a no-op.

**Reason:** Brickset is the source of truth for "how many do I own?" The user already saw that number in the preview ("import 3 → you'll own 3"). Recomputing the delta server-side at commit time turns the operation into an idempotent upsert.

#### F4 — Strip Brickset variant suffix when matching local rows

Brickset returns numbers like `10298-1` (variant 1 of set 10298). The duplicate-detection path in `main.py` import-preview uses this raw value to look up local rows, which were entered through the normal add flow as bare `10298`. Result: `local_qty=0` in the preview, duplicate rows on import.

**Change in `execution/brickset.py:_map_owned_set`:**

```python
# Before
set_number = s.get("number")

# After
raw = s.get("number", "")
set_number = raw.split("-")[0] if raw else raw
```

`brickset_set_id` continues to receive the full variant-suffixed string (Brickset needs the suffix for round-trip `fetch_set` calls). Only `set_number` (the local key) is normalised.

**Edge case:** Two Brickset variants (e.g. `10298-1` and `10298-2`) both map to `10298` locally. This is acceptable because the local data model already allows duplicates by primary key; the user differentiates with the `note` field.

### Cluster B — Photo lifecycle (2 fixes)

The DB row and the photo files in `uploads/{id}/` are tracked independently. Two paths leak files: delete-set leaves the folder behind, and edit-set leaves removed photos on disk.

#### S1 — Remove `uploads/{id}/` on delete

**Change in `navigation/set_manager.py:delete_set`:**

After the successful DELETE, add:

```python
import shutil
from pathlib import Path

UPLOADS_ROOT = Path(__file__).resolve().parent.parent / "uploads"
shutil.rmtree(UPLOADS_ROOT / str(set_id), ignore_errors=True)
```

`ignore_errors=True` because the folder may not exist (no own photos uploaded). `UPLOADS_ROOT` is defined module-level alongside the existing photo helpers.

#### S2 — Unlink removed photos on edit

When the user removes a photo on the edit page, the file currently stays on disk forever. `own_photos` shrinks, but the file lingers.

**Change in `navigation/set_manager.py:update_set`:**

Before issuing the UPDATE:

1. SELECT the existing `own_photos` value for the row.
2. JSON-parse it into `old_paths`.
3. Compute `removed = set(old_paths) - set(new_paths)`.
4. For each removed path, attempt `(UPLOADS_ROOT / path).unlink(missing_ok=True)` inside a try/except (do not let a missing file abort the update).

The unlink happens before the UPDATE so any failure surfaces before DB state changes. If the unlink raises an unexpected error, log it and continue (do not block the user's edit).

### Cluster C — Path-traversal hardening (1 fix)

#### F5 — Validate `session_id` shape in `/api/upload`

The upload route receives `session_id` from the client and uses it directly as a directory name under `/.tmp/uploads/`. A crafted value like `../../etc/passwd` would let a malicious page (or a future XSS hole) write outside the staging directory.

**Change in `main.py:api_upload`:**

```python
import re

SESSION_ID_RE = re.compile(r"[a-fA-F0-9-]{8,64}")  # module level

# Inside api_upload, before any filesystem work:
if not SESSION_ID_RE.fullmatch(session_id):
    return JSONResponse({"ok": False, "error": "invalid session_id"}, status_code=400)
```

The frontend already generates `session_id` via `crypto.randomUUID()`, which produces a 36-character lowercase-hex-with-hyphens string that comfortably passes the regex.

### Cluster D — UX gaps (3 fixes)

#### S3 — Wire up the dead duplicate-warning path (option A: info-only callout)

The `prefill["duplicates"]` key was added in Iteration 1 with the intent of warning the user when they're about to re-add a set they already own, but no code ever populates it and no template ever consumes it. Per the brainstorming discussion, we wire it up as a non-blocking info callout after a successful lookup.

**Change in `navigation/lookup_router.py:_flow1`** (and any sibling flow that produces a `prefill` dict for an existing-in-DB set):

After populating `prefill["brand"]` and `prefill["set_number"]`, look up `count = count_owned(brand, set_number)`. If `count >= 1`, set `prefill["duplicates"] = count`.

**Change in `templates/add.html:applyPrefill`** (JS):

Read `prefill.duplicates`. If truthy, render a small info-style callout above the form using existing callout markup. Reuse the existing callout component if there is one; otherwise inline a `<div class="callout callout-info">` matching the design system. The callout is informational (not blocking) — no buttons, no `disabled` form fields. User can still save normally.

**New i18n key:**

- `add.duplicate_warning`
  - `en`: `"You already own this set {count}×. Use the note field to differentiate."`
  - `de`: `"Du besitzt dieses Set bereits {count}×. Nutze das Notiz-Feld zur Unterscheidung."`

**Cleanup:** Delete the dead `errors.duplicate_warning` key in both locale files (it was never consumed).

#### S4 — Preserve `bs_qty=0` in the import preview

`main.py` currently builds the per-row preview with:

```python
bs_qty = s.get("qty_owned") or 1
```

When Brickset returns `qtyOwned: 0` (legitimate: user marked the set as previously owned but no longer), `or 1` flips that to 1, and the preview defaults to importing one copy of a set the API said zero of.

**Change:**

```python
bs_qty = s["qty_owned"] if s.get("qty_owned") is not None else 1
```

This mirrors the zero-preserving behaviour already in `_map_owned_set`. Missing/None still defaults to 1; explicit 0 stays 0 (and the preview row will display as such — user can manually adjust if they want).

#### S5 — Surface EAN-lookup status callouts on the edit page

The add page already handles lookup statuses (`not_found`, `ean_unresolved`, `rate_limit`, `error`) with a callout shown next to the EAN field. The edit page has its own EAN-rescan button (`doLookup`) but ignores the status, leaving the user with a silently-failed lookup.

**Change in `templates/edit.html:doLookup`** (JS):

Mirror the add page's existing status-handling block. Reuse the same i18n keys (`errors.ean_unresolved`, `errors.not_found`, `errors.rate_limit`, `errors.lookup_failed`). No new keys.

## Files Touched

| File | Reason |
|---|---|
| `templates/_brickset_import_preview.html` | F1 |
| `main.py` | F1 (pass dict), F2 (re-derive ids), F5 (regex validation), S4 (preserve 0) |
| `navigation/set_manager.py` | F3 (idempotency), S1 (delete cleanup), S2 (edit cleanup) |
| `execution/brickset.py` | F4 (strip suffix) |
| `navigation/lookup_router.py` | S3 (populate prefill) |
| `templates/add.html` | S3 (render callout) |
| `templates/edit.html` | S5 (status callout) |
| `locales/en.json`, `locales/de.json` | S3 (+1 key, -1 dead key) |
| `tests/...` | ~10 new tests |

## Test Plan (~10 new tests)

| # | Finding | Test |
|---|---|---|
| 1 | F1 | Render preview with Brickset name containing `</script>` — assert escaped (`<` becomes `<` in the embedded JSON). |
| 2 | F2 | Submit commit with tampered `local_ids_missing_bs_id` (ids belonging to a different brand/set_number) — assert those rows untouched. |
| 3 | F3 | Call commit-rows twice with same payload — assert second call inserts 0 rows. |
| 4 | F4 | `_map_owned_set({"number": "10298-1", ...})` → result `set_number == "10298"`, `brickset_set_id == "10298-1"`. |
| 5 | F5 | POST `/api/upload` with `session_id="../../etc/passwd"` → 400, no file created. |
| 6 | S1 | `delete_set(id)` → `uploads/{id}/` no longer exists on disk. |
| 7 | S2 | `update_set(id, own_photos=[shorter list])` → removed file unlinked. |
| 8 | S3 | `route_lookup` for a brand/set_number with `count_owned >= 1` → returns `prefill["duplicates"] == count`. |
| 9 | S4 | Build preview row with Brickset `qtyOwned: 0` → preview `bs_qty == 0`. |
| 10 | S5 | (manual smoke) Edit page → EAN rescan with unknown EAN → callout visible. |

Existing tests must still pass — particularly the existing commit/import flow tests (F2/F3 changes alter the internal contract but not the external behaviour for normal flows).

## Risk + Migration

- **No schema changes.** All fixes operate on existing tables.
- **No data migration.** Existing `uploads/{id}/` folders for already-deleted sets remain orphaned — not worth a one-off cleanup script.
- **Behaviour change visible to users:**
  - F3 changes commit semantics from delta to upsert. The preview UI still shows the same numbers, so the user experience is unchanged for first-time commits. Only retries and stale-preview cases differ — and they differ in the safe direction.
  - S3 adds a new info callout to the add page. No regression risk.
  - S4: a Brickset row with `qtyOwned: 0` now defaults to `bs_qty=0` in the preview (previously 1). User can still override.

## Done When

- All 10 fixes implemented as specified.
- ~10 new tests passing; existing test suite (~133 tests) still passing.
- Manual smoke: import flow, delete flow, edit flow, EAN rescan on edit, add page with already-owned set.
- One commit per fix (or per small group) with `fix:` / `refactor:` prefix matching repo style.

After this iteration, the next step is **Phase T** (LaunchAgent deployment), then V1.
