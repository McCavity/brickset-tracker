"""
Photo upload, staging, and finalisation.
See architecture/SOP-005-photo-upload.md.
"""
import logging
import os
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MAX_FILE_SIZE      = 20 * 1024 * 1024   # 20 MB
STAGING_TTL        = 3600               # 1 hour in seconds
# When BRICKSET_DATA_DIR is set: $BRICKSET_DATA_DIR/uploads (and uploads/staging within).
# When unset: ./uploads (current dev/LaunchAgent default — backward compatible).
_DATA_DIR    = Path(os.environ.get("BRICKSET_DATA_DIR", "."))
UPLOADS_ROOT = _DATA_DIR / "uploads"
STAGING_ROOT = UPLOADS_ROOT / "staging"


def upload_to_staging(file_bytes: bytes, filename: str, session_id: str) -> dict:
    """Save a photo to the staging area. Returns {ok, path, error}."""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {"ok": False, "error": f"Dateityp nicht erlaubt: {suffix}"}
    if len(file_bytes) > MAX_FILE_SIZE:
        return {"ok": False, "error": "Datei zu groß (max. 20 MB)"}

    staging_dir = STAGING_ROOT / session_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time() * 1000)
    safe_name = Path(filename).name.replace(" ", "_")
    dest = staging_dir / f"{ts}_{safe_name}"

    # Avoid collision
    counter = 1
    while dest.exists():
        dest = staging_dir / f"{ts}_{counter}_{safe_name}"
        counter += 1

    dest.write_bytes(file_bytes)
    relative = str(dest.relative_to(Path(".")))
    return {"ok": True, "path": relative}


def finalise_photos(session_id: str, set_id: int) -> list[str]:
    """Move staged photos to uploads/{set_id}/. Returns list of relative paths."""
    src_dir  = STAGING_ROOT / session_id
    dest_dir = UPLOADS_ROOT / str(set_id)

    if not src_dir.exists():
        return []

    dest_dir.mkdir(parents=True, exist_ok=True)
    final_paths = []

    for f in sorted(src_dir.iterdir()):
        dest = dest_dir / f.name
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{f.stem}_{counter}{f.suffix}"
            counter += 1
        shutil.move(str(f), str(dest))
        final_paths.append(str(dest.relative_to(Path("."))))

    try:
        src_dir.rmdir()
    except OSError:
        pass

    return final_paths


def cleanup_stale_staging() -> None:
    """Delete staging directories older than STAGING_TTL seconds."""
    if not STAGING_ROOT.exists():
        return
    now = time.time()
    for d in STAGING_ROOT.iterdir():
        if d.is_dir() and (now - d.stat().st_mtime) > STAGING_TTL:
            shutil.rmtree(d, ignore_errors=True)
            log.info("Cleaned stale staging dir: %s", d)
