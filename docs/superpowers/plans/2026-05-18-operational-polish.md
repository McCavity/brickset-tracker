# Operational Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `BRICKSET_DATA_DIR` env var (decouples data paths from project tree), a `.env.example` template, and public-facing `README.md` + MIT `LICENSE` at the repo root. Prepares brickset-tracker for GitHub publication without breaking the existing LaunchAgent install.

**Architecture:** `BRICKSET_DATA_DIR` is read at module-load time in `execution/db.py` and `execution/photos.py`, with fallback to the current paths (`./data` for the DB, `./uploads` for photos). New pytest tests use `importlib.reload` to verify both branches. The rest of the iteration is static files (`.env.example`, `LICENSE`, `README.md`, `docs/screenshots/.gitkeep`).

**Tech Stack:** Python 3.14 stdlib (`os.environ.get`, `importlib.reload`, `pathlib.Path`), pytest with `monkeypatch.setenv`/`delenv`, plain Markdown.

---

## File Structure

| File | Action |
|---|---|
| `execution/db.py` | Modify lines 7–8: read `BRICKSET_DATA_DIR` (default `"data"`). |
| `execution/photos.py` | Modify lines 15–16: read `BRICKSET_DATA_DIR` (default `"."`), link `STAGING_ROOT` to `UPLOADS_ROOT / "staging"`. |
| `tests/test_data_dir_env_var.py` | Create. 4 pytest cases. |
| `.env.example` | Create at repo root. |
| `LICENSE` | Create at repo root. MIT. |
| `README.md` | Create at repo root. ~200 lines, public-facing. |
| `docs/screenshots/.gitkeep` | Create so the folder exists for README image refs. |

## Task Order

1. **Task 1**: `BRICKSET_DATA_DIR` env var (TDD-driven: write tests first, then update db.py + photos.py). One commit.
2. **Task 2**: `.env.example` at repo root. One commit.
3. **Task 3**: `LICENSE` (MIT) at repo root. One commit.
4. **Task 4**: `README.md` + `docs/screenshots/.gitkeep`. One commit.
5. **Task 5**: Final verification + mark V1.1b done in `task_plan.md`. No commit (file is outside the repo).

5 tasks, 4 git commits, 4 new tests (157 total at the end).

---

## Task 1: `BRICKSET_DATA_DIR` env var

**Files:**
- Create: `tests/test_data_dir_env_var.py`
- Modify: `execution/db.py` (lines 7–8)
- Modify: `execution/photos.py` (lines 15–16)

### Step 1: Read the current `execution/db.py` to confirm line numbers

Before editing, confirm the current file shape:

```bash
sed -n '1,15p' execution/db.py
```

Expected output should show:
- Line 1: docstring/comment
- Lines around 4–7: imports (`import sqlite3`, `from pathlib import Path`, `from contextlib import contextmanager`)
- Line 8: `DB_PATH = Path("data/brickset.db")`

If the line numbers are different, use the file content to find the right block.

### Step 2: Read the current `execution/photos.py` similarly

```bash
sed -n '1,20p' execution/photos.py
```

Expected: lines 15–16 hold `STAGING_ROOT = Path("uploads/staging")` and `UPLOADS_ROOT = Path("uploads")`.

### Step 3: Write the failing tests

Create `tests/test_data_dir_env_var.py` with this exact content:

```python
"""BRICKSET_DATA_DIR env var rebases the SQLite DB and the uploads tree.

These tests use importlib.reload because the env var is read at module-load time.
The existing conftest.py `db` fixture uses monkeypatch.setattr on the module
attributes directly, so it is unaffected by reload-based tests.
"""
import importlib
from pathlib import Path


def test_db_path_uses_env_var(tmp_path, monkeypatch):
    """When BRICKSET_DATA_DIR is set, DB_PATH lives inside it."""
    monkeypatch.setenv("BRICKSET_DATA_DIR", str(tmp_path))
    from execution import db as db_module
    importlib.reload(db_module)
    assert db_module.DB_PATH == tmp_path / "brickset.db"


def test_uploads_root_uses_env_var(tmp_path, monkeypatch):
    """When BRICKSET_DATA_DIR is set, UPLOADS_ROOT and STAGING_ROOT live inside it."""
    monkeypatch.setenv("BRICKSET_DATA_DIR", str(tmp_path))
    from execution import photos as photos_module
    importlib.reload(photos_module)
    assert photos_module.UPLOADS_ROOT == tmp_path / "uploads"
    assert photos_module.STAGING_ROOT == tmp_path / "uploads" / "staging"


def test_db_path_defaults_when_env_var_unset(monkeypatch):
    """When BRICKSET_DATA_DIR is unset, DB_PATH falls back to ./data/brickset.db."""
    monkeypatch.delenv("BRICKSET_DATA_DIR", raising=False)
    from execution import db as db_module
    importlib.reload(db_module)
    assert db_module.DB_PATH == Path("data") / "brickset.db"


def test_uploads_root_defaults_when_env_var_unset(monkeypatch):
    """When BRICKSET_DATA_DIR is unset, UPLOADS_ROOT falls back to ./uploads."""
    monkeypatch.delenv("BRICKSET_DATA_DIR", raising=False)
    from execution import photos as photos_module
    importlib.reload(photos_module)
    assert photos_module.UPLOADS_ROOT == Path(".") / "uploads"
    assert photos_module.STAGING_ROOT == Path(".") / "uploads" / "staging"
```

### Step 4: Run the new tests to confirm they fail

```bash
.venv/bin/python -m pytest tests/test_data_dir_env_var.py -v
```

Expected: at least the two "uses_env_var" tests FAIL (current code ignores the env var). The two "defaults_when_env_var_unset" tests will PASS because the current hardcoded paths happen to match the expected fallback.

Don't be alarmed if you see exactly this mix: that's correct TDD red-phase output for this scenario.

### Step 5: Update `execution/db.py`

In `execution/db.py`, find the existing import block + `DB_PATH` constant near the top. The current content (lines 1–8 or thereabouts) looks like:

```python
"""
SQLite connection and schema setup.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("data/brickset.db")
```

Add `import os` to the existing imports (alphabetical order is fine), and replace the single `DB_PATH = ...` line with the two-line env-var version. The result:

```python
"""
SQLite connection and schema setup.
"""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DATA_DIR = Path(os.environ.get("BRICKSET_DATA_DIR", "data"))
DB_PATH = _DATA_DIR / "brickset.db"
```

Important: keep the rest of `db.py` unchanged. Don't reorder unrelated imports.

### Step 6: Update `execution/photos.py`

In `execution/photos.py`, find the current constants block (lines 15–16):

```python
STAGING_ROOT       = Path("uploads/staging")
UPLOADS_ROOT       = Path("uploads")
```

Replace with:

```python
# When BRICKSET_DATA_DIR is set: $BRICKSET_DATA_DIR/uploads (and uploads/staging within).
# When unset: ./uploads (current dev/LaunchAgent default — backward compatible).
_DATA_DIR    = Path(os.environ.get("BRICKSET_DATA_DIR", "."))
UPLOADS_ROOT = _DATA_DIR / "uploads"
STAGING_ROOT = UPLOADS_ROOT / "staging"
```

Add `import os` to the existing imports near the top of the file if it isn't already there:

```bash
grep -n "^import os" execution/photos.py
```

If no match, add `import os` alongside the existing imports (alphabetical: typically after `import logging` and before `import shutil`).

### Step 7: Run the new tests to confirm they pass

```bash
.venv/bin/python -m pytest tests/test_data_dir_env_var.py -v
```

Expected: all 4 tests PASS.

### Step 8: Run the full test suite to confirm no regression

```bash
.venv/bin/python -m pytest -q
```

Expected: `157 passed` (153 existing + 4 new).

If any existing test fails, the most likely cause is contamination from `importlib.reload` leaving the module in an inconsistent state. Verify:

```bash
.venv/bin/python -m pytest -q tests/test_db_fixture.py tests/test_db_py_lower.py
```

These directly exercise `execution.db`. They should pass — the conftest `db` fixture monkeypatches `DB_PATH` after reload, so the env-var-based default doesn't interfere.

If a regression DOES appear (unlikely but possible), check that the conftest fixture's `monkeypatch.setattr(db_module, "DB_PATH", test_db_path)` runs AFTER your `importlib.reload`. The pytest fixture order makes this automatic, but verify by running the failing test in isolation:

```bash
.venv/bin/python -m pytest -v <failing_test>
```

### Step 9: Verify the live LaunchAgent still works

The server is running as the LaunchAgent on port 8000 with `BRICKSET_DATA_DIR` unset (default behaviour). The env-var change is backward-compatible, but verify:

```bash
curl -s -o /dev/null -w "HTTP %{http_code} on /\n" http://localhost:8000/
```

Expected: `HTTP 200 on /`. If the LaunchAgent crashed because of an import error in db.py or photos.py, check logs:

```bash
tail -20 ~/Library/Logs/brickset-tracker.log
```

The LaunchAgent reads the new code on the next request (FastAPI's auto-reload is off, but each Python import goes through the live filesystem on cold-start of the worker). If you've made a syntax error, the smoke check will fail.

### Step 10: Commit

```bash
git add tests/test_data_dir_env_var.py execution/db.py execution/photos.py
git commit -m "feat(config): BRICKSET_DATA_DIR env var rebases DB + uploads (V1.1b)"
```

---

## Task 2: `.env.example`

**Files:**
- Create: `.env.example` at repo root.

### Step 1: Write `.env.example`

Create `/Users/hhalfpap/git/projects/own/brickset-tracker/.env.example` with EXACTLY this content:

```bash
# Brickset Tracker — environment configuration
# Copy this file to `.env` and fill in your own values.
# `.env` is gitignored; never commit real API keys.

# ── Brickset API ──────────────────────────────────────────────────────────
# Get an API key here: https://brickset.com/tools/webservices/v3/api
# Get your user hash by logging into Brickset and calling /login via their API.
BRICKSET_API_KEY=your-api-key-here
BRICKSET_USER_HASH=your-user-hash-here

# ── merlinssteine.de scraper ──────────────────────────────────────────────
# Maximum scrapes per day before the rate-limit guard kicks in.
# This protects merlinssteine.de from accidental DoS during bulk imports.
MERLINSSTEINE_DAILY_LIMIT=10

# ── Server ────────────────────────────────────────────────────────────────
# Port for the uvicorn server. The LaunchAgent install script auto-picks
# the next free port above this value if it's busy.
PORT=8000

# ── Data location ─────────────────────────────────────────────────────────
# Where the SQLite DB and photo uploads live. Leave unset to use the
# project-tree defaults (./data/brickset.db + ./uploads/).
# Example: ~/Library/Application Support/brickset-tracker
# BRICKSET_DATA_DIR=
```

### Step 2: Verify the file is NOT gitignored

```bash
git check-ignore .env.example; echo "exit=$?"
```

Expected: `exit=1` (NOT ignored — the gitignore rule `.env` is a literal filename match, not a prefix).

If `exit=0` (ignored), STOP — the gitignore rule needs updating to be more specific. (This shouldn't happen, but if it does, change `.env` in `.gitignore` to `/.env` to anchor it to the repo root, which still ignores the real `.env` without affecting `.env.example`.)

### Step 3: Verify the real `.env` is still gitignored

```bash
git check-ignore .env; echo "exit=$?"
```

Expected: `exit=0` (still ignored). Your real API keys stay out of the repo.

### Step 4: Verify the env vars in `.env.example` match what the app reads

Cross-check:

```bash
grep -hE "^[A-Z_]+=" .env.example | cut -d= -f1 | sort
```

Expected output:
```
BRICKSET_API_KEY
BRICKSET_USER_HASH
MERLINSSTEINE_DAILY_LIMIT
PORT
```

(`BRICKSET_DATA_DIR` is commented out so doesn't appear here. That's intentional — it's optional with a fallback.)

Now verify the app actually reads each of these:

```bash
grep -rn "os.environ" execution/ main.py 2>/dev/null
```

Expected: hits for `BRICKSET_API_KEY`, `BRICKSET_USER_HASH`, `MERLINSSTEINE_DAILY_LIMIT`, `BRICKSET_DATA_DIR` (the new one). `PORT` is read by `scripts/launchagent.sh`, not by Python — that's expected.

### Step 5: Commit

```bash
git add .env.example
git commit -m "docs: .env.example template for fresh-clone configuration (V1.1b)"
```

---

## Task 3: `LICENSE` (MIT)

**Files:**
- Create: `LICENSE` at repo root.

### Step 1: Write the LICENSE file

Create `/Users/hhalfpap/git/projects/own/brickset-tracker/LICENSE` with this exact content:

```
MIT License

Copyright (c) 2026 Henning Halfpap

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

### Step 2: Commit

```bash
git add LICENSE
git commit -m "docs: MIT license for public GitHub release (V1.1b)"
```

---

## Task 4: `README.md` + `docs/screenshots/.gitkeep`

**Files:**
- Create: `README.md` at repo root.
- Create: `docs/screenshots/.gitkeep`.

### Step 1: Create the screenshots placeholder folder

```bash
mkdir -p docs/screenshots
touch docs/screenshots/.gitkeep
```

### Step 2: Write `README.md` at the repo root

Create `/Users/hhalfpap/git/projects/own/brickset-tracker/README.md` with this exact content:

```markdown
# Brickset Tracker

A local-first SQLite-backed collection manager for LEGO and other brick brands, with Brickset.com integration and a bilingual German/English UI.

![Python](https://img.shields.io/badge/python-3.14-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Design](https://img.shields.io/badge/design-Verklemmt%20und%20zugen%C3%A4ht!-c45a3c)

![Collection list](docs/screenshots/01-collection-list.png)

## What it is

- A personal collection tracker for LEGO sets and other branded brick sets (Cobi, Lumibricks, Pantasy, MOCs, etc.).
- Local-first: runs entirely on your machine, stores everything in a single SQLite file + a folder of photos.
- Integrates with Brickset.com (when you provide a personal API key) and falls back to scraping merlinssteine.de for German LEGO catalog data.
- Auto-starts at login on macOS via a LaunchAgent.

## What it isn't

- A hosted service. The server binds to `127.0.0.1` only — no LAN exposure, no auth layer.
- A general-purpose inventory tool. Hard-coded around the brick-set domain (brand, set number, part count, etc.).
- Multi-user. One person, one machine.

## Key features

- Sorted + filterable collection list with full-text search across name, brand, set number, EAN, theme, note, location, condition, release year, and part count.
- EAN scan → metadata lookup, with Brickset and merlinssteine.de fallback.
- Bulk import from your Brickset.com collection (auto-detects existing local rows to avoid duplicates).
- Bilingual UI (German primary, English secondary), switchable per session.
- Photo uploads (your own) + automatic web-image fetch (display only — never stored).
- Multi-brand support beyond LEGO, with a configurable brand → URL slug map for the scraper.
- Background LaunchAgent (auto-start at login, auto-restart on crash, automatic free-port discovery).

## Screenshots

![Details view](docs/screenshots/02-details-view.png)

![Add flow](docs/screenshots/03-add-flow.png)

![Brand slug settings](docs/screenshots/04-brand-slug-settings.png)

![Brickset import preview](docs/screenshots/05-import-preview.png)

## Tech stack

- Python 3.14
- FastAPI 0.115 + Starlette 0.46
- SQLite (stdlib `sqlite3`)
- Jinja2 3.1
- Vanilla JavaScript (no framework, no build step)
- Lucide icons
- Custom "Verklemmt und zugenäht!" design system (handcrafted CSS in `static/style.css`)

## Quick start

```bash
git clone https://github.com/<your-username>/brickset-tracker.git
cd brickset-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env to add your Brickset API key + user hash
.venv/bin/uvicorn main:app --port 8000
```

Open <http://localhost:8000/> in a browser. The SQLite database is created on first request.

## Configuration

All configuration lives in `.env` (gitignored). Copy `.env.example` and fill in:

| Variable | Required | Default | Description |
|---|---|---|---|
| `BRICKSET_API_KEY` | yes | — | Get one at <https://brickset.com/tools/webservices/v3/api>. |
| `BRICKSET_USER_HASH` | yes | — | Returned by Brickset's `/login` API after you authenticate. |
| `MERLINSSTEINE_DAILY_LIMIT` | no | `10` | Scrape budget per day before the rate-limit guard kicks in. |
| `PORT` | no | `8000` | uvicorn port. The LaunchAgent installer auto-picks the next free port above this if busy. |
| `BRICKSET_DATA_DIR` | no | (project tree) | Parent directory for `brickset.db` + `uploads/`. Leave unset to keep data inside the project tree. |

## Running it

### Dev mode

```bash
.venv/bin/uvicorn main:app --reload --port 8000
```

The `--reload` flag watches files and restarts on changes. Use only during development.

### Production (macOS LaunchAgent)

Run the server as a background service that auto-starts at login and restarts on crash:

```bash
./scripts/launchagent.sh install
```

The install script also auto-discovers a free port (scanning upward from `PORT` in `.env`) and runs a smoke check. Status and uninstall commands are available — see [`scripts/README.md`](scripts/README.md) for operator details.

## Architecture overview

Three layers, named after a deliberate mnemonic — A.N.T.:

- **A**rchitecture (`architecture/`) — the eight SOPs that define the contract every change has to honour. Read these first if you want to extend the app.
- **N**avigation (`navigation/`) — routing and decision logic. `lookup_router.py` orchestrates EAN-to-set resolution; `set_manager.py` owns add/edit/delete and the search/filter query builder.
- **E**xecution (`execution/`) — deterministic, atomic scripts. `db.py` handles SQLite schema and connections; `photos.py` manages uploads and staging; `brickset.py` and `scraper.py` are the two external integrations.

The constitution lives in [`CLAUDE.md`](CLAUDE.md): data schema, behavioural rules, condition enum, language defaults, architectural invariants.

The SOPs:

- [SOP-001](architecture/SOP-001-add-set-workflow.md) — Add-set workflow
- [SOP-002](architecture/SOP-002-ean-resolution.md) — EAN resolution
- [SOP-003](architecture/SOP-003-merlinssteine-scraper.md) — merlinssteine.de scraper
- [SOP-004](architecture/SOP-004-brickset-api.md) — Brickset API
- [SOP-005](architecture/SOP-005-photo-upload.md) — Photo upload
- [SOP-006](architecture/SOP-006-rate-limit.md) — Rate limit
- [SOP-007](architecture/SOP-007-i18n.md) — i18n
- [SOP-008](architecture/SOP-008-database.md) — Database

## Testing

```bash
.venv/bin/python -m pytest -q
```

The project ships with ~157 tests covering route smoke, schema migrations, the Brickset import path, photo lifecycle, and i18n. Test factories are in `tests/factories.py`; the per-test SQLite fixture is in `tests/conftest.py`.

## Project status

- **V1 shipped 2026-05-18**: complete add/edit/delete/list/details/import flows, brand-slug settings, full pytest suite, LaunchAgent deployment.
- Active development for the maintainer's own use; PRs welcome but no guarantees on review timing.
- Iteration history lives in `docs/superpowers/plans/` (specs in `docs/superpowers/specs/`). Every shipped iteration has a spec → plan → execution audit trail.

## Contributing

This is a personal project, but PRs are welcome:

1. Open an issue first to discuss the change.
2. Fork, branch, commit.
3. Follow the spec/plan discipline: every non-trivial change starts with a spec in `docs/superpowers/specs/` and a plan in `docs/superpowers/plans/`.
4. Run `pytest -q` and confirm 0 regressions before opening the PR.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [Brickset.com](https://brickset.com) for their API and the LEGO catalog of record.
- [merlinssteine.de](https://www.merlinssteine.de) for the German-language LEGO catalog and the data we scrape as a backup.
- [Lucide](https://lucide.dev) for the icon set.
- [Claude Code](https://claude.com/claude-code) for AI-assisted development.
```

### Step 3: Verify Markdown renders cleanly

If you have `grip` installed (`pip install grip`):

```bash
grip README.md --browser
```

Otherwise, just visually inspect for obvious issues:

```bash
head -30 README.md
wc -l README.md
```

Expected: ~150–180 lines (the README is long but tight). The first 30 lines should include the title, tagline, badges row, and the hero image reference.

### Step 4: Verify the screenshots folder exists

```bash
ls -la docs/screenshots/
```

Expected: at least `.gitkeep` is present.

### Step 5: Verify all referenced screenshot paths exist (as either real files OR placeholders)

```bash
grep -oE 'docs/screenshots/[^)]*' README.md | sort -u
```

Expected output (5 paths):
```
docs/screenshots/01-collection-list.png
docs/screenshots/02-details-view.png
docs/screenshots/03-add-flow.png
docs/screenshots/04-brand-slug-settings.png
docs/screenshots/05-import-preview.png
```

None of these PNGs need to exist yet — the user will capture them after launch. Markdown will gracefully degrade to broken image refs (alt text shown).

### Step 6: Verify the badge URLs are valid

```bash
grep -oE 'https://img.shields.io[^)]*' README.md
```

Expected output (3 badges):
```
https://img.shields.io/badge/python-3.14-blue
https://img.shields.io/badge/license-MIT-green
https://img.shields.io/badge/design-Verklemmt%20und%20zugen%C3%A4ht!-c45a3c
```

These should all render as colored chips on GitHub. (Shields.io static badges work offline by hitting their CDN at view time.)

### Step 7: Commit

```bash
git add README.md docs/screenshots/.gitkeep
git commit -m "docs: public-facing README with quick-start, config, and architecture overview (V1.1b)"
```

---

## Task 5: Mark V1.1b done in `task_plan.md`

**Files:**
- Modify: `~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md` (outside the repo).

### Step 1: Locate the "Road to V1" section in the task plan

The Road-to-V1 list currently ends with `10. **V1 done** ✅ 2026-05-18 — usable small local server, running as a LaunchAgent`. Below it, add a new section for V1.1 work.

### Step 2: Add the V1.1b entry

In `task_plan.md`, after the Road-to-V1 list ending with item 10, add a new section:

```markdown
## V1.1 — post-V1 polish

11. ~~**Iteration 4.3** — lightbox mouse navigation (regression fix + click zones)~~ **✅ COMPLETE 2026-05-18** (153 tests, +2 commits, template/CSS only)
12. ~~**V1.1b** — operational polish (BRICKSET_DATA_DIR env var + .env.example + public README + MIT LICENSE)~~ **✅ COMPLETE 2026-05-18** (157 tests, +4 commits, prepared repo for GitHub publication)
```

If the file ALREADY has a V1.1 section from the Iteration 4.3 close-out, just add line 12 underneath the existing line 11. Verify first:

```bash
grep -n "V1.1\|Iteration 4.3" ~/.claude/projects/-Users-hhalfpap-git-projects-own-brickset-tracker/memory/task_plan.md
```

If grep returns a "V1.1" section header, add line 12 inside it. Otherwise, create the section as shown above.

### Step 3: No git commit

`task_plan.md` lives outside the repo. No commit needed.

---

## Final Verification

- [ ] **Step 1: Four new commits since the spec**

```bash
cd /Users/hhalfpap/git/projects/own/brickset-tracker
git log --oneline 9f19728..HEAD
```

Expected (four commits, most recent first):
- `<sha> docs: public-facing README with quick-start, config, and architecture overview (V1.1b)`
- `<sha> docs: MIT license for public GitHub release (V1.1b)`
- `<sha> docs: .env.example template for fresh-clone configuration (V1.1b)`
- `<sha> feat(config): BRICKSET_DATA_DIR env var rebases DB + uploads (V1.1b)`

- [ ] **Step 2: Repo-root file inventory**

```bash
ls -la README.md LICENSE .env.example docs/screenshots/.gitkeep
```

Expected: all four files exist.

- [ ] **Step 3: pytest green**

```bash
.venv/bin/python -m pytest -q
```

Expected: `157 passed`.

- [ ] **Step 4: LaunchAgent still running on port 8000**

```bash
./scripts/launchagent.sh status
```

Expected: HTTP 200, server responding.

- [ ] **Step 5: `.env` is still gitignored; `.env.example` is committed**

```bash
git check-ignore .env; echo ".env ignored=$?"
git check-ignore .env.example 2>/dev/null; echo ".env.example ignored=$?"
git ls-files | grep -E "^(\.env\.example|LICENSE|README\.md|docs/screenshots/\.gitkeep)$"
```

Expected:
- `.env ignored=0` (yes, ignored)
- `.env.example ignored=1` (NOT ignored)
- The grep returns 4 file paths.

V1.1b is done.
