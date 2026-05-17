"""S2 — update_set must unlink files that the user removed from own_photos."""
import json
from pathlib import Path

from execution.db import get_connection
from navigation.set_manager import update_set
from tests.factories import make_set


def test_update_set_unlinks_removed_photos(db, tmp_path, monkeypatch):
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    set_id = make_set()
    # Two pre-existing photos on disk + in DB.
    own_dir = tmp_path / "uploads" / str(set_id)
    own_dir.mkdir(parents=True)
    keep_path = f"uploads/{set_id}/keep.jpg"
    drop_path = f"uploads/{set_id}/drop.jpg"
    (tmp_path / keep_path).write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / drop_path).write_bytes(b"\xff\xd8\xff\xd9")
    with get_connection() as conn:
        conn.execute(
            "UPDATE sets SET own_photos=? WHERE id=?",
            (json.dumps([keep_path, drop_path]), set_id),
        )

    # User edits the set, removing `drop.jpg` (sends only `keep.jpg`).
    update_set(set_id, {
        "brand": "LEGO", "set_number": "0000", "name": "Test Set", "part_count": 100,
        "existing_own_photos": json.dumps([keep_path]),
    })

    assert (tmp_path / keep_path).exists()
    assert not (tmp_path / drop_path).exists()


def test_update_set_tolerates_already_missing_files(db, tmp_path, monkeypatch):
    """If a file the DB still lists is already gone from disk, update must not raise."""
    from execution import photos as photos_module
    monkeypatch.setattr(photos_module, "UPLOADS_ROOT", tmp_path / "uploads")

    set_id = make_set()
    ghost_path = f"uploads/{set_id}/ghost.jpg"
    with get_connection() as conn:
        conn.execute(
            "UPDATE sets SET own_photos=? WHERE id=?",
            (json.dumps([ghost_path]), set_id),
        )
    # No file on disk. User removes the entry — must not crash.
    update_set(set_id, {
        "brand": "LEGO", "set_number": "0000", "name": "Test Set", "part_count": 100,
        "existing_own_photos": json.dumps([]),
    })
