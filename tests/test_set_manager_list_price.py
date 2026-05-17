"""save_set / update_set / get_sets / get_set round-trip list_price."""
from navigation.set_manager import save_set, update_set, get_set, get_sets


def test_save_set_persists_list_price(db):
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": 99.99,
    })
    set_id = result["id"]
    row = get_set(set_id)
    assert row["list_price"] == 99.99


def test_save_set_accepts_german_decimal_in_list_price(db):
    """Same German-or-dot parsing as price_paid (via the _float helper)."""
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": "99,99",
    })
    set_id = result["id"]
    row = get_set(set_id)
    assert row["list_price"] == 99.99


def test_save_set_with_no_list_price_stores_null(db):
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106,
    })
    set_id = result["id"]
    row = get_set(set_id)
    assert row["list_price"] is None


def test_update_set_persists_list_price(db):
    from tests.factories import make_set
    set_id = make_set(brand="LEGO", set_number="10298", name="V", part_count=1)
    update_set(set_id, {
        "brand": "LEGO", "set_number": "10298", "name": "V",
        "part_count": 1106, "list_price": 199.99,
        "existing_own_photos": "[]",
    })
    row = get_set(set_id)
    assert row["list_price"] == 199.99


def test_update_set_can_clear_list_price(db):
    """Saving an empty list_price clears the column to NULL."""
    result = save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": 99.99,
    })
    set_id = result["id"]
    update_set(set_id, {
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": "",
        "existing_own_photos": "[]",
    })
    row = get_set(set_id)
    assert row["list_price"] is None


def test_get_sets_returns_list_price(db):
    """list_price is in the SELECT column list, so it flows through
    to the list-view rendering layer."""
    save_set({
        "brand": "LEGO", "set_number": "10298", "name": "Vespa",
        "part_count": 1106, "list_price": 99.99,
    })
    rows = get_sets()
    assert len(rows) == 1
    assert rows[0]["list_price"] == 99.99
