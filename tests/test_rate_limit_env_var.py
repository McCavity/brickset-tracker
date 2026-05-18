"""MERLINSSTEINE_DAILY_LIMIT env var controls the merlinssteine scrape quota.

Like the BRICKSET_DATA_DIR tests, these use importlib.reload because the env
var is read at module-load time when execution.rate_limit's LIMITS dict is
populated.
"""
import importlib


def test_merlinssteine_limit_uses_env_var(monkeypatch):
    """MERLINSSTEINE_DAILY_LIMIT=42 → LIMITS['merlinssteine'] == 42."""
    monkeypatch.setenv("MERLINSSTEINE_DAILY_LIMIT", "42")
    from execution import rate_limit
    importlib.reload(rate_limit)
    assert rate_limit.LIMITS["merlinssteine"] == 42


def test_merlinssteine_limit_defaults_to_10(monkeypatch):
    """Unset MERLINSSTEINE_DAILY_LIMIT → falls back to 10 (historical default)."""
    monkeypatch.delenv("MERLINSSTEINE_DAILY_LIMIT", raising=False)
    from execution import rate_limit
    importlib.reload(rate_limit)
    assert rate_limit.LIMITS["merlinssteine"] == 10
    # Sibling limits should be unaffected by the env var.
    assert rate_limit.LIMITS["brickset"] == 100
    assert rate_limit.LIMITS["upcitemdb"] == 100
