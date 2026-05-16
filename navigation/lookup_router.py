"""
Routes between Flow 1 (set number known) and Flow 2 (EAN only).
See architecture/SOP-001-add-set-workflow.md.
"""
import logging

from execution.db import get_connection
from execution.ean_lookup import resolve_ean
from execution.scraper import brand_to_slug, scrape_set
from execution.brickset import fetch_set

log = logging.getLogger(__name__)


async def route_lookup(
    ean: str | None = None,
    brand: str | None = None,
    set_number: str | None = None,
) -> dict:
    """
    Determine lookup flow and return pre-fill data for the add form.
    Returns {status, prefill: dict, message: str, candidates: list}.
    """
    # Flow 1: brand + set_number known
    if brand and set_number:
        return await _flow1(brand.strip(), set_number.strip(), ean)

    # Flow 2: EAN only
    if ean:
        ean = ean.strip().replace(" ", "").replace("-", "")

        # Check local cache first
        cached = _ean_cache_lookup(ean)
        if cached:
            log.info("EAN cache hit: %s → %s / %s", ean, cached["brand"], cached["set_number"])
            return await _flow1(cached["brand"], cached["set_number"], ean)

        # External EAN resolution
        result = await resolve_ean(ean)

        if result["status"] == "resolved" and result.get("brand") and result.get("set_number"):
            _ean_cache_write(ean, result["brand"], result["set_number"], "upcitemdb")
            return await _flow1(result["brand"], result["set_number"], ean)

        if result["status"] == "ambiguous":
            return {
                "status":     "ambiguous",
                "candidates": result.get("candidates", []),
                "prefill":    {"ean": ean},
            }

        # Unresolved — return EAN pre-filled, ask user for brand+set_number
        return {
            "status":  "ean_unresolved",
            "prefill": {"ean": ean},
            "message": "EAN nicht erkannt. Bitte Marke und Set-Nummer eingeben.",
        }

    return {"status": "empty", "prefill": {}}


async def _flow1(brand: str, set_number: str, ean: str | None = None) -> dict:
    """Flow 1: scrape merlinssteine.de, optionally enrich from Brickset."""
    slug   = brand_to_slug(brand)
    result = await scrape_set(slug, set_number)

    prefill: dict = {"brand": brand, "set_number": set_number}
    if ean:
        prefill["ean"] = ean

    if result["status"] == "success":
        prefill.update({
            "name":         result.get("name"),
            "part_count":   result.get("part_count"),
            "theme":        result.get("theme"),
            "release_year": result.get("release_year"),
            "price_paid":   result.get("price"),
            "ean":          result.get("ean") or ean,
            "web_images":   [result["image_url"]] if result.get("image_url") else [],
            "brand":        result.get("brand_full") or brand,
        })
        # Cache the EAN if we just learned it
        if result.get("ean") and not ean:
            _ean_cache_write(result["ean"], prefill["brand"], set_number, "merlinssteine")

        # LEGO enrichment via Brickset
        if "lego" in brand.lower():
            bs = await fetch_set(set_number)
            if bs["status"] == "found":
                prefill.setdefault("theme",        bs.get("theme"))
                prefill.setdefault("release_year", bs.get("year"))
                prefill["brickset_set_id"] = bs.get("set_id")
                if not prefill.get("web_images") and bs.get("image_url"):
                    prefill["web_images"] = [bs["image_url"]]

        return {"status": "success", "prefill": prefill}

    if result["status"] == "rate_limit":
        return {
            "status":  "rate_limit",
            "prefill": prefill,
            "message": "Tageslimit für merlinssteine.de erreicht. Bitte manuell eingeben.",
        }

    if result["status"] == "not_found":
        return {
            "status":  "not_found",
            "prefill": prefill,
            "message": "Set nicht auf merlinssteine.de gefunden. Bitte manuell eingeben.",
        }

    return {
        "status":  "error",
        "prefill": prefill,
        "message": "Fehler beim Abrufen der Daten. Bitte manuell eingeben.",
    }


def _ean_cache_lookup(ean: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT brand, set_number FROM ean_cache WHERE ean=?", (ean,)
        ).fetchone()
    return dict(row) if row else None


def _ean_cache_write(ean: str, brand: str, set_number: str, source: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO ean_cache (ean, brand, set_number, source)
               VALUES (?, ?, ?, ?)""",
            (ean, brand, set_number, source),
        )
