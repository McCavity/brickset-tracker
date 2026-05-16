# SOP-003 — merlinssteine.de Scraper

**Layer:** Tool (execution)
**Goal:** Fetch a set's full metadata from merlinssteine.de by constructing the canonical URL from brand slug + set number. Rate-limited to 10 requests per calendar day.

---

## Input
```
brand_slug:  string  — lowercase, e.g. "bb", "lego", "cobi"
set_number:  string  — brand-internal number, e.g. "107916", "42172-1"
```

## Output
```
{
  "status":       "success" | "not_found" | "rate_limit" | "error",
  "name":         string | null,
  "ean":          string | null,
  "part_count":   integer | null,
  "price":        float | null,
  "theme":        string | null,
  "release_year": integer | null,
  "image_url":    string | null,   # CDN URL for main product image
  "brand_full":   string | null,   # Full brand name as shown on page
  "raw_url":      string           # URL that was fetched
}
```

---

## Brand Slug Mapping (known prefixes)

| Brand | Slug |
|---|---|
| BlueBrixx | bb |
| LEGO | lego |
| Cobi | cobi |
| Mould King | mk (confirm via test) |
| Cada | cada (confirm via test — alphanumeric set numbers may 404) |

The mapping is maintained in `execution/scraper.py` as a dict. Unknown brands use the lowercased brand name as a guess and handle 404 gracefully.

---

## Steps

```
1. Call SOP-006: check_quota()
   └─ Quota exhausted → return status = "rate_limit" immediately (no HTTP request)

2. Construct URL:
   url = f"https://www.merlinssteine.de/sets/{brand_slug}-{set_number}/"

3. HTTP GET with:
   - User-Agent: "BricksetTracker/1.0 (personal collection tool; +contact@example.com)"
   - Timeout: 10 seconds
   - No cookies, no session

4. Call SOP-006: increment_quota()  ← counted on every HTTP attempt (success or 4xx)
   - Not counted on connection errors (network unreachable, DNS failure)

5. Response handling:
   ├─ 200 OK  → parse HTML (step 6)
   ├─ 404     → return status = "not_found"
   ├─ 429     → return status = "rate_limit" (server-side throttle)
   └─ Other   → return status = "error" with HTTP status code

6. Parse HTML with BeautifulSoup:
   Extract the following fields (CSS selectors TBD from live page inspection):
   - name:         page <h1> or structured data
   - ean:          table row labelled "EAN" or "Barcode"
   - part_count:   row labelled "Teile" or "Steine"
   - price:        row labelled "Preis" (strip "€", convert to float)
   - theme:        row labelled "Thema" or breadcrumb
   - release_year: row labelled "Erscheinungsjahr" or release date field
   - image_url:    CDN pattern: cdn.merlinssteine.de/images/{BRAND_UPPER}-{SET_NUMBER}/main/...
   - brand_full:   row labelled "Hersteller" or "Marke"

7. Validate: if name is empty after parsing, treat as "error" (page structure may have changed).

8. Log to .tmp/scraper.log: timestamp, url, status, fields_found.

9. Return structured result to SOP-001.
```

---

## Rate Limit Behaviour

- Counter stored in `scrape_quota` SQLite table (see SOP-006).
- Limit: 10 per calendar day (midnight local time reset).
- User-facing message when limit reached: shown in UI, offers manual entry fallback.
- The 10/day limit applies across all brands — it is a global daily budget.

---

## Edge Cases

| Situation | Behaviour |
|---|---|
| Unknown brand slug → 404 | Return status="not_found"; note in response that slug may be wrong |
| Alphanumeric set number (e.g. CaDA "C71009W") → 404 | Same as above |
| Page structure changed (fields not found) | Return status="error"; log which fields were missing |
| LEGO set number with variant suffix (e.g. "42172-1" vs "42172") | Try with suffix first; if 404, retry without suffix (costs 2 quota) |
| Connection timeout | Return status="error"; do NOT increment quota counter |
| Redirect (3xx) | Follow up to 3 redirects; if destination is not a set page, treat as 404 |
