"""
EAN resolution via UPCitemdb and Open Products Facts.
See architecture/SOP-002-ean-resolution.md.
"""
import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path

import httpx

from execution.rate_limit import check_quota, increment_quota

log = logging.getLogger(__name__)


async def resolve_ean(ean: str) -> dict:
    """
    Attempt to resolve an EAN to (brand, set_number).
    Returns: {status, brand, set_number, name, candidates}
    """
    if not re.fullmatch(r"\d{8,14}", ean):
        return {"status": "unresolved", "reason": "invalid_format"}

    upc_result, opf_result = await asyncio.gather(
        _try_upcitemdb(ean),
        _try_opf(ean),
        return_exceptions=True,
    )

    candidates = []
    for res in (upc_result, opf_result):
        if isinstance(res, dict) and res.get("name"):
            candidates.append(res)

    if not candidates:
        return {"status": "unresolved"}

    if len(candidates) == 1 or _same(candidates):
        c = candidates[0]
        return {
            "status":     "resolved",
            "brand":      c.get("brand"),
            "set_number": c.get("set_number"),
            "name":       c.get("name"),
        }

    return {"status": "ambiguous", "candidates": candidates}


async def _try_upcitemdb(ean: str) -> dict:
    if not check_quota("upcitemdb"):
        return {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                "https://api.upcitemdb.com/prod/trial/lookup",
                params={"upc": ean},
            )
        increment_quota("upcitemdb")
        _log(ean, "upcitemdb", r.status_code)
        items = r.json().get("items", [])
        if not items:
            return {}
        item = items[0]
        return {
            "name":       item.get("title"),
            "brand":      item.get("brand"),
            "set_number": _extract_set_number(item.get("title", ""), item.get("brand", "")),
            "source":     "upcitemdb",
        }
    except Exception as e:
        log.debug("UPCitemdb error: %s", e)
        return {}


async def _try_opf(ean: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"https://world.openproductsfacts.org/api/v2/product/{ean}.json"
            )
        _log(ean, "opf", r.status_code)
        if r.status_code != 200:
            return {}
        body = r.json()
        if body.get("status") != 1:
            return {}
        p = body.get("product", {})
        name = p.get("product_name") or p.get("product_name_en") or p.get("product_name_de")
        if not name:
            return {}
        brand = p.get("brands", "").split(",")[0].strip()
        return {
            "name":       name,
            "brand":      brand or None,
            "set_number": _extract_set_number(name, brand),
            "source":     "opf",
        }
    except Exception as e:
        log.debug("OPF error: %s", e)
        return {}


def _extract_set_number(title: str, brand: str) -> str | None:
    brand_l = (brand or "").lower()
    # LEGO: number often in title like "LEGO 42172" or "42172"
    if "lego" in brand_l or "lego" in title.lower():
        m = re.search(r"\b(\d{4,6}(?:-\d)?)\b", title)
        return m.group(1) if m else None
    # BlueBrixx: 6-digit number
    if "bluebrixx" in brand_l:
        m = re.search(r"\b(\d{6})\b", title)
        return m.group(1) if m else None
    return None


def _same(candidates: list[dict]) -> bool:
    names = {c.get("name", "").lower().strip() for c in candidates}
    return len(names) == 1


def _log(ean: str, source: str, status: int) -> None:
    Path(".tmp").mkdir(exist_ok=True)
    with open(".tmp/ean_lookup.log", "a") as f:
        f.write(f"{datetime.now().isoformat()} | {source} | {ean} | {status}\n")
