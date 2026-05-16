"""_map_owned_set extends _map_set with qtyOwned extraction from the
collection object Brickset returns on owned-flagged getSets calls."""
from execution.brickset import _map_owned_set


def test_extracts_qty_owned():
    raw = {
        "setID": 23456, "number": "10298", "name": "Vespa 125",
        "pieces": 1106, "theme": "Creator Expert", "year": 2022,
        "barcode": {"EAN": "5702016912661"},
        "image": {"imageURL": "https://example.com/v.jpg"},
        "collection": {"owned": True, "qtyOwned": 3},
    }
    r = _map_owned_set(raw)
    assert r["qty_owned"] == 3
    assert r["set_number"] == "10298"
    assert r["set_id"] == 23456
    assert r["name"] == "Vespa 125"
    assert r["pieces"] == 1106
    assert r["theme"] == "Creator Expert"
    assert r["year"] == 2022
    assert r["ean"] == "5702016912661"
    assert r["image_url"] == "https://example.com/v.jpg"


def test_defaults_qty_owned_to_one():
    """When the collection object is missing or qtyOwned is null."""
    raw = {"setID": 1, "number": "10298", "name": "X", "pieces": 1}
    assert _map_owned_set(raw)["qty_owned"] == 1

    raw_with_null = {**raw, "collection": {"qtyOwned": None}}
    assert _map_owned_set(raw_with_null)["qty_owned"] == 1

    raw_with_zero = {**raw, "collection": {"qtyOwned": 0}}
    # Zero is a valid response — respect it
    assert _map_owned_set(raw_with_zero)["qty_owned"] == 0


def test_uses_number_field_for_set_number():
    """Brickset's bare set number lives in the top-level 'number' field,
    not in setNumber (which it doesn't expose)."""
    raw = {"setID": 1, "number": "10298-1", "name": "X", "pieces": 1}
    r = _map_owned_set(raw)
    assert r["set_number"] == "10298-1"
