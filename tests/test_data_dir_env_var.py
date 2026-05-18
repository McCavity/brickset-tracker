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
