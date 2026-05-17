"""F5 — /api/upload must reject session_id values that aren't UUID-shaped."""
from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_rejects_path_traversal_session_id(db, tmp_path, monkeypatch):
    """A '../' in session_id must yield 400 and write no file outside staging."""
    from main import app
    from execution import photos as photos_module

    monkeypatch.setattr(photos_module, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "../../etc/passwd"},
        )

    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    # Nothing should have been written anywhere under tmp_path.
    written = list((tmp_path).rglob("*"))
    assert not any(p.is_file() for p in written)


def test_upload_accepts_uuid_shaped_session_id(db, tmp_path, monkeypatch):
    """A standard 36-char UUID session_id (matches crypto.randomUUID())
    must continue to succeed."""
    from main import app
    from execution import photos as photos_module

    monkeypatch.setattr(photos_module, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    with TestClient(app) as client:
        r = client.post(
            "/api/upload",
            files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
            data={"session_id": "550e8400-e29b-41d4-a716-446655440000"},
        )

    assert r.status_code == 200
    assert r.json()["ok"] is True
