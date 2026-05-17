"""F5 — /api/upload must reject session_id values that aren't UUID-shaped."""
from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_rejects_path_traversal_session_id(db):
    """A '../' in session_id must yield 400 and not proceed to upload_to_staging."""
    from main import app

    client = TestClient(app)
    r = client.post(
        "/api/upload",
        files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
        data={"session_id": "../../etc/passwd"},
    )

    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "invalid session_id"


def test_upload_accepts_uuid_shaped_session_id(db):
    """A standard 36-char UUID session_id (matches crypto.randomUUID())
    must continue to succeed."""
    from main import app

    client = TestClient(app)
    r = client.post(
        "/api/upload",
        files={"file": ("x.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
        data={"session_id": "550e8400-e29b-41d4-a716-446655440000"},
    )

    assert r.status_code == 200
    assert r.json()["ok"] is True
