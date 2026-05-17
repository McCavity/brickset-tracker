"""After Task 2's scraper rename, the lookup router must route the
extracted list_price into prefill['list_price'] and must NOT touch
prefill['price_paid']. Brickset's list_price fills gaps."""
import pytest

from navigation import lookup_router


# Test 1: merlinssteine result → prefill["list_price"]; price_paid untouched

def test_merge_from_merlinssteine_writes_list_price():
    prefill = {"brand": "LEGO", "set_number": "42171"}
    result = {
        "status": "success",
        "name": "McLaren P1",
        "part_count": 3893,
        "theme": "Technic",
        "release_year": 2023,
        "list_price": 449.99,
        "ean": "5702017595672",
    }
    lookup_router._merge_from_merlinssteine(prefill, result)
    assert prefill["list_price"] == 449.99
    assert "price_paid" not in prefill, "price_paid must remain unset (per design A)"


def test_merge_from_merlinssteine_handles_missing_list_price():
    """If merlinssteine didn't extract a list price, prefill stays free of the key."""
    prefill = {"brand": "BlueBrixx", "set_number": "10000"}
    result = {"status": "success", "name": "Castle", "part_count": 500}
    lookup_router._merge_from_merlinssteine(prefill, result)
    assert "list_price" not in prefill
    assert "price_paid" not in prefill


# Test 2: Brickset gap-fills list_price; doesn't overwrite an existing one

def test_merge_from_brickset_fills_list_price_when_missing():
    prefill = {"brand": "LEGO", "set_number": "10298"}
    bs = {
        "set_id":     23456,
        "name":       "Vespa 125",
        "pieces":     1106,
        "theme":      "Creator Expert",
        "year":       2022,
        "list_price": 99.99,
    }
    lookup_router._merge_from_brickset(prefill, bs)
    assert prefill["list_price"] == 99.99
    assert "price_paid" not in prefill


def test_merge_from_brickset_does_not_overwrite_existing_list_price():
    """merlinssteine wins where it has data; Brickset only fills gaps."""
    prefill = {"brand": "LEGO", "set_number": "10298", "list_price": 89.99}
    bs = {"set_id": 1, "name": "X", "list_price": 99.99}
    lookup_router._merge_from_brickset(prefill, bs)
    assert prefill["list_price"] == 89.99  # merlinssteine's value won


def test_merge_from_brickset_handles_missing_list_price():
    prefill = {"brand": "LEGO", "set_number": "10298"}
    bs = {"set_id": 1, "name": "X"}  # no list_price key
    lookup_router._merge_from_brickset(prefill, bs)
    assert "list_price" not in prefill
