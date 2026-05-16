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
    """Fetch LEGO set metadata from Brickset by set number."""
    if not check_quota("brickset"):
        return {"status": "quota_exceeded"}

    params = json.dumps({"setNumber": set_number})
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{BASE}/getSets", data={
                "apiKey": API_KEY, "userHash": USER_HASH, "params": params
            })
    except httpx.RequestError as e:
        log.warning("Brickset network error: %s", e)
        return {"status": "error"}

    increment_quota("brickset")

    body = r.json()
    if body.get("status") != "success":
        return {"status": "error", "message": body.get("message")}

    sets = body.get("sets", [])

    # Try without variant suffix if nothing found
    if not sets and "-" in set_number:
        base_num = set_number.split("-")[0]
        return await fetch_set(base_num)

    if not sets:
        return {"status": "not_found"}

    if len(sets) > 1:
        return {
            "status":     "ambiguous",
            "candidates": [_map_set(s) for s in sets],
        }

    return {"status": "found", **_map_set(sets[0])}


async def sync_owned(set_id: int, qty_owned: int) -> dict:
    """Mark a set as owned on Brickset with the given quantity."""
    params = json.dumps({"own": 1, "qtyOwned": qty_owned, "want": 0, "notes": " "})
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


def _map_set(s: dict) -> dict:
    barcode = s.get("barcode") or {}
    img     = s.get("image") or {}
    return {
        "set_id":    s.get("setID"),
        "name":      s.get("name"),
        "pieces":    s.get("pieces"),
        "theme":     s.get("theme"),
        "year":      s.get("year"),
        "ean":       barcode.get("EAN"),
        "image_url": img.get("imageURL"),
    }


def _log_sync(set_id: int, qty: int, status: str) -> None:
    Path(".tmp").mkdir(exist_ok=True)
    with open(".tmp/brickset_sync.log", "a") as f:
        f.write(f"{datetime.now().isoformat()} | setID={set_id} qty={qty} → {status}\n")
