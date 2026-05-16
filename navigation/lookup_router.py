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
    """Flow 1: gather metadata from merlinssteine.de and (for LEGO) Brickset.

    Both sources are tried independently for LEGO. merlinssteine wins for
    fields it returns; Brickset fills any gaps and is the sole source of
    ``brickset_set_id``. Status is ``success`` if at least one source
    returned data — so a 2026 LEGO set Brickset knows but merlinssteine
    doesn't will still come back populated.
    """
    slug = brand_to_slug(brand)

    prefill: dict = {"brand": brand, "set_number": set_number}
    if ean:
        prefill["ean"] = ean

    # ── merlinssteine.de scrape ─────────────────────────────────────
    ms_result    = await scrape_set(slug, set_number)
    ms_succeeded = ms_result["status"] == "success"

    if ms_succeeded:
        _merge_from_merlinssteine(prefill, ms_result)
        if ms_result.get("ean") and not ean:
            _ean_cache_write(ms_result["ean"], prefill["brand"], set_number, "merlinssteine")

    # ── Brickset enrichment (LEGO only — always tried) ─────────────
    bs_succeeded = False
    if "lego" in brand.lower():
        bs_result = await fetch_set(set_number)
        if bs_result["status"] == "found":
            _merge_from_brickset(prefill, bs_result)
            if bs_result.get("ean") and not prefill.get("ean"):
                _ean_cache_write(bs_result["ean"], prefill["brand"], set_number, "brickset")
            bs_succeeded = True

    # ── Compose response ───────────────────────────────────────────
    if ms_succeeded or bs_succeeded:
        return {"status": "success", "prefill": prefill}

    # Both sources failed — surface merlinssteine's status as the user-facing reason
    if ms_result["status"] == "rate_limit":
        return {
            "status":  "rate_limit",
            "prefill": prefill,
            "message": "Tageslimit für merlinssteine.de erreicht. Bitte manuell eingeben.",
        }

    if ms_result["status"] == "not_found":
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


def _merge_from_merlinssteine(prefill: dict, result: dict) -> None:
    """Copy merlinssteine fields into prefill, only when they have truthy values."""
    field_map = (
        ("name",         result.get("name")),
        ("part_count",   result.get("part_count")),
        ("theme",        result.get("theme")),
        ("release_year", result.get("release_year")),
        ("price_paid",   result.get("price")),
    )
    for key, value in field_map:
        if value:
            prefill[key] = value

    if result.get("ean"):
        prefill["ean"] = result["ean"]
    if result.get("image_url"):
        prefill["web_images"] = [result["image_url"]]
    if result.get("brand_full"):
        prefill["brand"] = result["brand_full"]


def _merge_from_brickset(prefill: dict, bs: dict) -> None:
    """Copy Brickset fields into prefill, filling only the gaps merlinssteine left.

    `brickset_set_id` is always set (Brickset is the authoritative source).
    """
    field_map = (
        ("name",         bs.get("name")),
        ("part_count",   bs.get("pieces")),
        ("theme",        bs.get("theme")),
        ("release_year", bs.get("year")),
    )
    for key, value in field_map:
        if value and not prefill.get(key):
            prefill[key] = value

    if bs.get("ean") and not prefill.get("ean"):
        prefill["ean"] = bs["ean"]
    if not prefill.get("web_images") and bs.get("image_url"):
        prefill["web_images"] = [bs["image_url"]]

    prefill["brickset_set_id"] = bs.get("set_id")


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
