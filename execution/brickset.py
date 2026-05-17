"""
Brickset API client — fetch metadata and sync owned status.
See architecture/SOP-004-brickset-api.md.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from execution.rate_limit import check_quota, increment_quota

load_dotenv()
log = logging.getLogger(__name__)

API_KEY   = os.getenv("BRICKSET_API_KEY", "")
USER_HASH = os.getenv("BRICKSET_USER_HASH", "")
BASE      = "https://brickset.com/api/v3.asmx"


async def fetch_set(set_number: str) -> dict:
    """Fetch LEGO set metadata from Brickset by set number.

    Brickset's getSets API matches setNumber exactly, and its canonical form
    includes a variant suffix (e.g. ``42225-1``). To accept the bare set
    number users normally type, we try a list of candidates in order and
    return the first hit.
    """
    candidates = (
        [set_number] if "-" in set_number
        else [f"{set_number}-1", set_number]
    )

    for candidate in candidates:
        if not check_quota("brickset"):
            return {"status": "quota_exceeded"}

        result = await _query(candidate)
        if result["status"] != "ok":
            # Network error or upstream non-success — give up early.
            return {"status": "error", "message": result.get("message")}

        sets = result["sets"]
        if not sets:
            continue  # Try next candidate

        if len(sets) > 1:
            return {
                "status":     "ambiguous",
                "candidates": [_map_set(s) for s in sets],
            }

        return {"status": "found", **_map_set(sets[0])}

    return {"status": "not_found"}


async def _query(set_number: str) -> dict:
    """One Brickset getSets call. Consumes one quota point on every call.

    Returns {"status": "ok", "sets": [...]} on success or
    {"status": "error", "message": ...} on network/API failure.
    """
    params = json.dumps({"setNumber": set_number})
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{BASE}/getSets", data={
                "apiKey": API_KEY, "userHash": USER_HASH, "params": params,
            })
    except httpx.RequestError as e:
        log.warning("Brickset network error: %s", e)
        return {"status": "error", "message": str(e)}

    increment_quota("brickset")

    body = r.json()
    if body.get("status") != "success":
        return {"status": "error", "message": body.get("message")}

    return {"status": "ok", "sets": body.get("sets", [])}


async def sync_owned(set_id: int, qty_owned: int) -> dict:
    """Mark a set as owned on Brickset with the given quantity.

    Sends only `qtyOwned` in the params object — Brickset infers ownership
    from a non-zero count. Including the `own` field alongside `qtyOwned`
    has a server-side quirk where `own: 1` overrides `qtyOwned` and the
    final stored count is clamped to 1.
    """
    params = json.dumps({"qtyOwned": qty_owned})
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{BASE}/setCollection", data={
                "apiKey": API_KEY, "userHash": USER_HASH,
                "setID": set_id, "params": params,
            })
    except httpx.RequestError as e:
        log.warning("Brickset sync network error: %s", e)
        return {"status": "error"}

    body = r.json()
    result = {"status": body.get("status", "error")}
    _log_sync(set_id, qty_owned, result["status"])
    return result


PAGE_SIZE = 100


async def fetch_owned_collection() -> dict:
    """Return all LEGO sets the user owns on Brickset.

    Pages through getSets with owned=1 until fewer than PAGE_SIZE results
    return. Each page consumes one quota point. The "next page is empty"
    case (when the total is an exact multiple of PAGE_SIZE) costs one
    extra quota point — acceptable for V1.

    Returns:
        {"status": "ok", "sets": [...]}        on success
        {"status": "quota_exceeded"}           if quota is exhausted before any call
        {"status": "error", "message": "..."}  on network/API failure
    """
    all_sets: list[dict] = []
    page = 1

    while True:
        if not check_quota("brickset"):
            return {"status": "quota_exceeded"}

        params = json.dumps({
            "owned":      1,
            "pageSize":   PAGE_SIZE,
            "pageNumber": page,
        })
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(f"{BASE}/getSets", data={
                    "apiKey": API_KEY, "userHash": USER_HASH, "params": params,
                })
        except httpx.RequestError as e:
            log.warning("Brickset network error: %s", e)
            return {"status": "error", "message": str(e)}

        increment_quota("brickset")

        body = r.json()
        if body.get("status") != "success":
            return {"status": "error", "message": body.get("message")}

        page_sets = body.get("sets", [])
        all_sets.extend(_map_owned_set(s) for s in page_sets)

        if len(page_sets) < PAGE_SIZE:
            break
        page += 1

    return {"status": "ok", "sets": all_sets}


def _map_set(s: dict) -> dict:
    barcode = s.get("barcode") or {}
    img     = s.get("image") or {}
    lego_de = (s.get("LEGOCom") or {}).get("DE") or {}
    return {
        "set_id":     s.get("setID"),
        "name":       s.get("name"),
        "pieces":     s.get("pieces"),
        "theme":      s.get("theme"),
        "year":       s.get("year"),
        "ean":        barcode.get("EAN"),
        "image_url":  img.get("imageURL"),
        "list_price": lego_de.get("retailPrice"),
    }


def _map_owned_set(s: dict) -> dict:
    """Extension of _map_set that also extracts qtyOwned from the collection
    object Brickset returns when the request includes the user's userHash.

    The 'set_number' returned here is the bare number from Brickset's 'number'
    field with any '-N' variant suffix stripped — used for matching against
    local rows by brand+set_number (which users typically enter without suffix).
    """
    base = _map_set(s)
    coll = s.get("collection") or {}
    qty  = coll.get("qtyOwned")
    base["qty_owned"]   = 1 if qty is None else qty
    raw_number = s.get("number") or ""
    base["set_number"]  = raw_number.split("-", 1)[0]
    return base


def _log_sync(set_id: int, qty: int, status: str) -> None:
    Path(".tmp").mkdir(exist_ok=True)
    with open(".tmp/brickset_sync.log", "a") as f:
        f.write(f"{datetime.now().isoformat()} | setID={set_id} qty={qty} → {status}\n")
