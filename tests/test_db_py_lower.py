"""py_lower is a Python-backed SQLite function that handles Unicode
case-folding properly (SQLite's built-in LOWER is ASCII-only)."""
from execution.db import get_connection


def test_py_lower_ascii(db):
    with get_connection() as conn:
        result = conn.execute("SELECT py_lower('HELLO')").fetchone()[0]
    assert result == "hello"


def test_py_lower_umlauts(db):
    with get_connection() as conn:
        result = conn.execute("SELECT py_lower('MÖBEL')").fetchone()[0]
    assert result == "möbel"


def test_py_lower_handles_null(db):
    with get_connection() as conn:
        result = conn.execute("SELECT py_lower(NULL)").fetchone()[0]
    assert result is None
