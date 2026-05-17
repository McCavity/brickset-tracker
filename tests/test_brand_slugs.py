"""brand_slugs module: CRUD helpers + brand_to_slug() with DB-backed lookup."""
import pytest
import sqlite3

from execution.brand_slugs import (
    brand_to_slug,
    list_brand_slugs,
    add_brand_slug,
    ensure_brand_slug,
    update_brand_slug,
    delete_brand_slug,
)


# ── brand_to_slug ──────────────────────────────────────────────────────────

def test_brand_to_slug_returns_seeded_value(db):
    assert brand_to_slug("LEGO") == "lego"
    assert brand_to_slug("Pantasy") == "pant"


def test_brand_to_slug_normalises_input(db):
    assert brand_to_slug("  LEGO  ") == "lego"
    assert brand_to_slug("PANTASY") == "pant"
    assert brand_to_slug("BlueBrixx") == "bb"


def test_brand_to_slug_falls_back_for_unknown(db):
    assert brand_to_slug("Some New Brand") == "some-new-brand"
    assert brand_to_slug("Ikea") == "ikea"


# ── list_brand_slugs ───────────────────────────────────────────────────────

def test_list_brand_slugs_returns_sorted_pairs(db):
    pairs = list_brand_slugs()
    brands = [p["brand"] for p in pairs]
    assert brands == sorted(brands)
    assert len(pairs) >= 8  # at least the seed entries


# ── add_brand_slug ─────────────────────────────────────────────────────────

def test_add_brand_slug_inserts(db):
    add_brand_slug("Foo Brand", "foo")
    assert brand_to_slug("foo brand") == "foo"


def test_add_brand_slug_normalises(db):
    add_brand_slug("  IKEA  ", "  IK  ")
    assert brand_to_slug("ikea") == "ik"


def test_add_brand_slug_duplicate_raises(db):
    with pytest.raises(sqlite3.IntegrityError):
        add_brand_slug("LEGO", "different-slug")


# ── ensure_brand_slug ──────────────────────────────────────────────────────

def test_ensure_brand_slug_inserts_when_missing(db):
    ensure_brand_slug("Foo", "f")
    assert brand_to_slug("foo") == "f"


def test_ensure_brand_slug_noop_when_present(db):
    """ensure_brand_slug never overwrites an existing seeded value."""
    ensure_brand_slug("LEGO", "different-slug")
    assert brand_to_slug("lego") == "lego"  # original seed wins


# ── update_brand_slug ──────────────────────────────────────────────────────

def test_update_brand_slug_changes_slug(db):
    update_brand_slug("LEGO", "LG")
    assert brand_to_slug("lego") == "lg"


def test_update_brand_slug_for_missing_brand_is_noop(db):
    """No exception, no row created."""
    update_brand_slug("NonexistentBrand", "x")
    assert brand_to_slug("nonexistentbrand") == "nonexistentbrand"  # fallback


# ── delete_brand_slug ──────────────────────────────────────────────────────

def test_delete_brand_slug_removes_row(db):
    delete_brand_slug("LEGO")
    assert brand_to_slug("lego") == "lego"  # falls back to default


def test_delete_brand_slug_for_missing_brand_is_noop(db):
    delete_brand_slug("NonexistentBrand")  # must not raise
