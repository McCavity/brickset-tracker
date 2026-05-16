"""Shared pytest fixtures."""
import sqlite3
from pathlib import Path

import pytest

from execution import db as db_module
from execution.db import init_db


@pytest.fixture
def db(tmp_path: Path, monkeypatch) -> Path:
    """Per-test SQLite database in a temp file.

    Monkeypatches execution.db.DB_PATH so any code calling
    get_connection() during the test uses the temp DB. The temp
    file is cleaned up automatically when the test exits.
    """
    test_db_path = tmp_path / "test_brickset.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db_path)
    init_db()
    yield test_db_path
