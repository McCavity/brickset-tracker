"""S1 — delete_set must remove the on-disk uploads/{id}/ folder."""
import shutil
from pathlib import Path

from execution.db import get_connection
from navigation.set_manager import delete_set
from tests.factories import make_set


def test_delete_set_removes_uploads_directory(db, tmp_path, monkeypatch):
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")
    # set_manager imports UPLOADS_ROOT lazily inside delete_set, so patching
    # the source module is sufficient.

    set_id = make_set()
    own_dir = tmp_path / "uploads" / str(set_id)
    own_dir.mkdir(parents=True)
    (own_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    delete_set(set_id)

    assert not own_dir.exists()
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM sets WHERE id=?", (set_id,)).fetchone()
    assert row is None


def test_delete_set_without_uploads_directory_is_silent(db, tmp_path, monkeypatch):
    """If the set has no uploaded photos (no folder), delete must still succeed."""
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    set_id = make_set()  # No uploads/{id}/ folder.
    delete_set(set_id)   # Must not raise.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM sets WHERE id=?", (set_id,)).fetchone()
    assert row is None
