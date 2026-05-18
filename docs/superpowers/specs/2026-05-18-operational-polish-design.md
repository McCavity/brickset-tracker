# Operational Polish — Design

**Status:** Approved 2026-05-18
**Project:** brickset-tracker
**Iteration:** V1.1b (operational polish for public GitHub release)

## Goal

Make brickset-tracker safe for future-you to revisit after 18 months AND clean for a public GitHub release. Three deliverables:
1. `BRICKSET_DATA_DIR` env var to decouple "where the code lives" from "where the data lives."
2. `.env.example` template so a fresh clone can be configured without reading source.
3. Public-facing `README.md` + MIT `LICENSE` at the repo root.

After this iteration ships, the repo is ready to push public.

## Out of Scope

- Migration script for moving existing data into a new `BRICKSET_DATA_DIR` (manual `mv` is fine for V1).
- Publishing the "Verklemmt und zugenäht!" design system to its own repo — deferred to V2 handoff.
- Screenshots — README will reference image paths under `docs/screenshots/`; the user captures them after launch. Missing images render as broken refs (acceptable for now).
- npm package, Docker image, CI pipeline — out of scope.

## Files Touched

| File | Action |
|---|---|
| `execution/db.py` | Modify lines 7–8: read `BRICKSET_DATA_DIR` env var, default to `"data"`. |
| `execution/photos.py` | Modify lines 15–16: read same env var, default to `"."`. Link `STAGING_ROOT` to `UPLOADS_ROOT / "staging"`. |
| `tests/test_data_dir_env_var.py` | Create. Four pytest cases for env-var behaviour (set + unset, each for DB and uploads). |
| `.env.example` | Create at repo root. Template with placeholder values for all five env vars. |
| `README.md` | Create at repo root. Public-facing, ~200 lines. |
| `LICENSE` | Create at repo root. MIT, your name + year 2026. |
| `docs/screenshots/.gitkeep` | Create so the folder exists for README image references. |

## Part 1: `BRICKSET_DATA_DIR` env var

### Behaviour

| Env var state | DB path | Uploads path |
|---|---|---|
| Unset (current default) | `./data/brickset.db` | `./uploads/` |
| Set to `/X` | `/X/brickset.db` | `/X/uploads/` |

`BRICKSET_DATA_DIR` is the *parent* directory of both `brickset.db` and `uploads/`, not a flat container. This lets you e.g. put everything under `~/Library/Application Support/brickset-tracker/` with `brickset.db` and `uploads/` as siblings.

### `execution/db.py` change

Replace lines 7–8 (after the existing imports):

```python
import os
from pathlib import Path

_DATA_DIR = Path(os.environ.get("BRICKSET_DATA_DIR", "data"))
DB_PATH = _DATA_DIR / "brickset.db"
```

Note the default: when unset, `_DATA_DIR = Path("data")` → `DB_PATH = Path("data/brickset.db")`. Identical to current behaviour.

### `execution/photos.py` change

Replace lines 15–16:

```python
# When BRICKSET_DATA_DIR is set: $BRICKSET_DATA_DIR/uploads (and uploads/staging within).
# When unset: ./uploads (current dev/LaunchAgent default — backward compatible).
_DATA_DIR    = Path(os.environ.get("BRICKSET_DATA_DIR", "."))
UPLOADS_ROOT = _DATA_DIR / "uploads"
STAGING_ROOT = UPLOADS_ROOT / "staging"
```

The asymmetric default value (`"data"` in `db.py`, `"."` in `photos.py`) is intentional: `db.py`'s historical layout had the DB inside `./data/`, while `photos.py`'s historical layout had uploads inside `./uploads/` directly. The fallback preserves both.

### Tests (`tests/test_data_dir_env_var.py`)

```python
"""BRICKSET_DATA_DIR env var rebases the SQLite DB and the uploads tree."""
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

Four tests total. They use `importlib.reload` because the env var is read at module-load time.

**Order-of-execution concern:** these tests reload modules, which could affect other tests run in the same process. The reload restores the previous behaviour cleanly (env var is restored by monkeypatch when the test exits, and any subsequent test that touches `db_module.DB_PATH` either monkeypatches it directly via the existing `db` fixture or reloads itself). Verified that the existing `db` fixture (`tests/conftest.py`) uses `monkeypatch.setattr(db_module, "DB_PATH", ...)` which works AFTER reload — the new fixture path overrides the env-var-derived one. No cross-test contamination expected.

## Part 2: `.env.example`

Committed template at the repo root. `.env` stays gitignored (current `.gitignore:1` rule covers it; `.env.example` is NOT matched because `.env` in gitignore is a literal filename, not a prefix).

Content:

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

## Part 3: `LICENSE`

Standard MIT, single file at repo root:

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

## Part 4: `README.md`

Public-facing, ~200 lines. Section structure (each section gets ~10–25 lines):

### 1. Header + tagline
- `# Brickset Tracker`
- Tagline: "A local-first SQLite-backed collection manager for LEGO and other brick brands, with Brickset.com integration and a bilingual German/English UI."
- Badges row: Python 3.14, MIT license, and the decorative "Verklemmt und zugenäht!" design-system chip:
  ```
  ![Python](https://img.shields.io/badge/python-3.14-blue)
  ![License](https://img.shields.io/badge/license-MIT-green)
  ![Design](https://img.shields.io/badge/design-Verklemmt%20und%20zugen%C3%A4ht!-c45a3c)
  ```

### 2. Hero screenshot
- `![Collection list](docs/screenshots/01-collection-list.png)`
- Placeholder — broken image until the user captures it.

### 3. What it is + what it isn't (two short bullet lists)

### 4. Key features (~7 bullets)
Sorted/filterable collection list, EAN scan lookup (Brickset + merlinssteine.de fallback), Brickset bulk import, bilingual UI, photo uploads + web image fetch, multi-brand support, background LaunchAgent.

### 5. Screenshots gallery
Four placeholder image refs: details view, add flow, brand-slug settings, import preview.

### 6. Tech stack (bulleted, ~6 items)

### 7. Quick start (copy-pasteable code blocks)
```bash
git clone <url>
cd brickset-tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env to add your Brickset API key + user hash
.venv/bin/uvicorn main:app --port 8000
# Open http://localhost:8000/
```

### 8. Configuration — env vars table
| Variable | Required | Default | Description |
|---|---|---|---|
| `BRICKSET_API_KEY` | yes | — | Get from brickset.com/tools/webservices/v3/api |
| `BRICKSET_USER_HASH` | yes | — | From the Brickset `/login` API |
| `MERLINSSTEINE_DAILY_LIMIT` | no | `10` | Scrape budget per day |
| `PORT` | no | `8000` | uvicorn port |
| `BRICKSET_DATA_DIR` | no | (project tree) | Where DB + uploads live |

### 9. Running it
- 9a. Dev: `uvicorn main:app --reload --port 8000`
- 9b. Production (LaunchAgent on macOS): link to `scripts/README.md`

### 10. Architecture overview
3 paragraphs covering A.N.T. layers (Architecture / Navigation / Execution), the data model summary, and the constitution in `CLAUDE.md`. Links to all 8 SOPs in `architecture/`.

### 11. Testing
- `.venv/bin/python -m pytest -q` → ~157 tests
- Note about `tests/conftest.py` fixtures and `tests/factories.py`

### 12. Project status
- V1 shipped 2026-05-18
- Link to `docs/superpowers/plans/` for iteration history
- "Active development for the maintainer's own use; PRs welcome but no guarantees on review timing"

### 13. Contributing (brief)
Open an issue, fork, follow the spec/plan iteration discipline.

### 14. License
"MIT — see [LICENSE](LICENSE)"

### 15. Acknowledgments
Brickset.com, merlinssteine.de, Lucide, Claude Code.

## Part 5: `docs/screenshots/`

Create the folder with a `.gitkeep` so the path exists for README references. The user captures actual PNGs after launch.

## Testing Strategy

- **Part 1**: 4 new pytest tests (`test_data_dir_env_var.py`). Existing 153 must still pass. New total: 157.
- **Parts 2–4**: no automated tests (static files). Manual smoke:
  - `.env.example` is committed and visible on a fresh clone.
  - `README.md` and `LICENSE` render correctly on GitHub (preview locally with `grip` or just trust GFM).
  - The LaunchAgent server keeps running through the iteration (no migration triggered because `BRICKSET_DATA_DIR` stays unset by default).

## Risk + Migration

- **Backward compatibility**: env-var fallback means existing dev environments + the live LaunchAgent keep working untouched. No migration needed unless you choose to move the data later.
- **Module-load-time read**: env var is read once, at import. Changing `.env` requires a server restart. Acceptable for V1.1.
- **Existing `db` fixture interaction**: the conftest fixture monkeypatches `db_module.DB_PATH` directly. New env-var tests use `importlib.reload(db_module)`. The two patterns coexist cleanly because each test sets up its own fixture state.
- **No data migration script** — V1.1 is too small. Manual `mv data uploads "$BRICKSET_DATA_DIR/"` + restart is the upgrade path if you ever choose to relocate.

## Done When

- `execution/db.py` and `execution/photos.py` read `BRICKSET_DATA_DIR` with fallback to current defaults.
- 4 new tests pass; 157 total.
- `.env.example` exists at repo root, committed.
- `README.md` exists at repo root, committed, with placeholder screenshot refs and env-vars table.
- `LICENSE` (MIT) exists at repo root, committed.
- `docs/screenshots/.gitkeep` committed.
- Live LaunchAgent server still running on port 8000 with the same DB/uploads (no migration required).
- V1.1b marked complete in `task_plan.md`.
