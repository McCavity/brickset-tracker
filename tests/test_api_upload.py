"""F5 — /api/upload must reject session_id values that aren't UUID-shaped.

These tests focus on F5's contract: rejection of bad session_id shapes.
The happy-path upload flow is covered by Iteration 1's photo tests and
manual smoke; F5 itself is purely a guard-clause check, so the rejection
tests run without any filesystem isolation (the guard returns 400 before
touching disk).
"""
from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_rejects_path_traversal_session_id(db):
    """A '../' in session_id must yield 400 and write no file to staging."""
    from main import app
    from execution.photos import STAGING_ROOT

    before_files = set(STAGING_ROOT.rglob("*")) if STAGING_ROOT.exists() else set()

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "../../etc/passwd"},
        )

    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "invalid session_id"

    # The guard runs before any file I/O — staging contents must be
    # unchanged. (Also: a literal "../../etc/passwd" directory must not
    # have been created under STAGING_ROOT.)
    after_files = set(STAGING_ROOT.rglob("*")) if STAGING_ROOT.exists() else set()
    assert after_files == before_files
    assert not (STAGING_ROOT / "..").resolve().joinpath("etc/passwd").exists()


def test_upload_rejects_empty_session_id(db):
    """An empty session_id must also be rejected (regex requires ≥8 chars)."""
    from main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": ""},
        )

    # FastAPI's Form(...) requires a value, so empty may yield 422 from
    # the framework or 400 from our guard. Either is acceptable as long
    # as it's not 200 and no file was written.
    assert r.status_code in (400, 422)


def test_upload_rejects_too_short_session_id(db):
    """A 7-char session_id (below the 8-char minimum) must be rejected."""
    from main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "abc-123"},
        )

    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_upload_rejects_disallowed_characters(db):
    """A session_id containing characters outside [a-fA-F0-9-] must be rejected."""
    from main import app

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "550e8400_e29b_41d4_a716_446655440000"},  # underscores
        )

    assert r.status_code == 400
    assert r.json()["ok"] is False
