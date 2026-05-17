"""
merlinssteine.de scraper.
See architecture/SOP-003-merlinssteine-scraper.md.
"""
import re
import logging
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from execution.rate_limit import check_quota, increment_quota

log = logging.getLogger(__name__)

BRAND_SLUGS: dict[str, str] = {
    "bluebrixx":  "bb",
    "blue brixx": "bb",
    "lego":       "lego",
    "cobi":       "cobi",
    "mould king": "mk",
    "cada":       "cada",
    "lumibricks": "lumi",
    "funwhole":   "lumi",   # Lumibricks former name
    "pantasy":    "pant",
}

UA = "BricksetTracker/1.0 (personal collection tool; single-user)"
BASE = "https://www.merlinssteine.de"


def brand_to_slug(brand: str) -> str:
    return BRAND_SLUGS.get(brand.lower().strip(), brand.lower().strip().replace(" ", "-"))


async def scrape_set(brand_slug: str, set_number: str) -> dict:
    """
    Fetch set metadata from merlinssteine.de.
    Returns a structured result dict with status key.
    """
    if not check_quota("merlinssteine"):
        return {"status": "rate_limit"}

    url = f"{BASE}/sets/{brand_slug}-{set_number.lower()}/"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            r = await client.get(url, headers={"User-Agent": UA})
    except httpx.RequestError as e:
        log.warning("Scrape network error for %s: %s", url, e)
        # Network errors do NOT consume quota
        return {"status": "error", "raw_url": url}

    increment_quota("merlinssteine")
    _log_scrape(url, r.status_code)

    if r.status_code == 404:
        return {"status": "not_found", "raw_url": url}
    if r.status_code == 429:
        return {"status": "rate_limit", "raw_url": url}
    if r.status_code != 200:
        return {"status": "error", "raw_url": url, "http_status": r.status_code}

    return _parse(r.text, url)


def _parse(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # --- Name from H1 ---
    h1 = soup.find("h1")
    name = None
    if h1:
        raw = h1.get_text(strip=True)
        # "BlueBrixx - Herrenhaus des Astronomen | Set 107916"
        if " | Set " in raw:
            raw = raw.split(" | Set ")[0]
        if " - " in raw:
            raw = raw.split(" - ", 1)[1]
        name = raw.strip()

    if not name:
        return {"status": "error", "reason": "could not parse name", "raw_url": url}

    # --- Details UL (after h2 "Details") ---
    details_h2 = soup.find("h2", string=re.compile(r"Details", re.I))
    data: dict[str, str] = {}
    if details_h2:
        details_ul = details_h2.find_next("ul")
        if details_ul:
            for li in details_ul.find_all("li"):
                text = li.get_text(separator=" ", strip=True)
                if ": " in text:
                    key, _, val = text.partition(": ")
                    data[key.strip().lower()] = val.strip()

    ean        = data.get("ean")
    brand_full = data.get("von")
    release    = data.get("release", "")
    theme      = data.get("kategorie")
    release_year = _parse_year(release)

    # --- Parts UL (li ending with "Teile") ---
    part_count = None
    for ul in soup.find_all("ul"):
        for li in ul.find_all("li"):
            m = re.match(r"^([\d.,]+)\s+Teile$", li.get_text(strip=True))
            if m:
                part_count = int(m.group(1).replace(".", "").replace(",", ""))
                break
        if part_count:
            break

    # --- List price (Listenpreis) ---
    list_price = None
    for ul in soup.find_all("ul"):
        for li in ul.find_all("li"):
            text = li.get_text(strip=True)
            if text.startswith("Listenpreis:"):
                m = re.search(r"([\d.,]+)\s*EUR", text)
                if m:
                    list_price = _parse_price(m.group(1))
                break

    # --- Image (OG tag, then CDN fallback) ---
    og_img = soup.find("meta", property="og:image")
    image_url = og_img["content"] if og_img and og_img.get("content") else None
    if not image_url:
        slug_upper = url.split("/sets/")[1].rstrip("/").upper()
        image_url = f"https://cdn.merlinssteine.de/images/{slug_upper}/main/{slug_upper}.webp"

    return {
        "status":       "success",
        "name":         name,
        "ean":          ean,
        "part_count":   part_count,
        "list_price":   list_price,
        "theme":        theme,
        "release_year": release_year,
        "image_url":    image_url,
        "brand_full":   brand_full,
        "raw_url":      url,
    }


def _parse_price(raw: str) -> float | None:
    """Convert a price string to float, handling both German (1.595,01) and
    dot-decimal (219.99) formats. Rule: if a comma is present it's German format;
    otherwise a dot followed by exactly 2 digits is the decimal point."""
    if not raw:
        return None
    if "," in raw:
        # German format: dots = thousands sep, comma = decimal
        return float(raw.replace(".", "").replace(",", "."))
    # Dot-decimal format (e.g. "219.99") or plain integer (e.g. "220")
    # A dot followed by 3 digits is a thousands separator, not decimal
    parts = raw.rsplit(".", 1)
    if len(parts) == 2 and len(parts[1]) == 3:
        return float(parts[0].replace(".", "") + parts[1])  # e.g. "1.595" → 1595.0
    return float(raw)


def _parse_year(text: str) -> int | None:
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return int(m.group(0)) if m else None


def _log_scrape(url: str, status: int) -> None:
    Path(".tmp").mkdir(exist_ok=True)
    with open(".tmp/scraper.log", "a") as f:
        f.write(f"{datetime.now().isoformat()} | {status} | {url}\n")
