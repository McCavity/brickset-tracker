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


def test_upload_accepts_uuid_shaped_session_id(db, tmp_path, monkeypatch):
    """A standard 36-char UUID session_id (matches crypto.randomUUID())
    must continue to succeed. Guards against future regex tightening that
    would silently break the frontend."""
    import os
    from main import app

    # Let lifespan run first (it loads locales from real cwd), then chdir
    # to tmp_path so upload_to_staging's relative STAGING_ROOT (and its
    # downstream relative_to(Path(".")) call) both resolve under the
    # isolated temp tree. Restore the original cwd before exiting so other
    # tests aren't affected.
    with TestClient(app) as client:
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            r = client.post(
                "/api/upload",
                files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
                data={"session_id": "550e8400-e29b-41d4-a716-446655440000"},
            )
            ok = r.json()
            written_path = tmp_path / ok["path"] if ok.get("ok") else None
        finally:
            os.chdir(original_cwd)

    assert r.status_code == 200
    assert ok["ok"] is True
    # The returned path starts with "uploads/staging/{session_id}/"
    assert ok["path"].startswith("uploads/staging/550e8400-e29b-41d4-a716-446655440000/")
    # And the file actually landed under tmp_path (not the real project tree).
    assert written_path is not None and written_path.exists()
