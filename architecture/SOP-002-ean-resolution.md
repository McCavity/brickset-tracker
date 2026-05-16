# SOP-002 — EAN Resolution

**Layer:** Tool (execution)
**Goal:** Attempt to resolve a raw EAN-13 string to a (brand, set_number) pair using external services. Always returns a result — either resolved data or an explicit "unresolved" signal.

---

## Input
```
ean: string  — 13-digit EAN, digits only, no spaces or dashes
```

## Output
```
{
  "status":     "resolved" | "ambiguous" | "unresolved",
  "brand":      string | null,
  "set_number": string | null,
  "name":       string | null,
  "candidates": list | null   # only when status = "ambiguous"
}
```

---

## Steps

```
1. Validate EAN format: must be 13 digits. Reject anything else immediately.

2. Check ean_cache table in SQLite.
   └─ Hit → return status="resolved" with cached brand + set_number (no external call)

3. Fire UPCitemdb and Open Products Facts in parallel (asyncio.gather):
   ├─ UPCitemdb:          GET https://api.upcitemdb.com/prod/trial/lookup?upc={ean}
   └─ Open Products Facts: GET https://world.openproductsfacts.org/api/v2/product/{ean}.json

4. Collect results:
   ├─ Both empty          → status = "unresolved"
   ├─ One result          → extract brand + name; attempt to derive set_number (see below)
   └─ Conflicting results → status = "ambiguous"; return candidates list to user

5. Set number derivation from product name:
   - Pattern match for known formats:
     - LEGO:      look for "LEGO" in brand field; set_number often in title (e.g. "LEGO 42172")
     - BlueBrixx: look for "BlueBrixx" or "Blue Brixx" in brand
     - Fallback:  return name only; user must confirm/correct set_number manually

6. Write resolved mapping to ean_cache (only on status = "resolved").

7. Return result to SOP-001.
```

---

## Rate Limits & Error Handling

| Service | Limit | On failure |
|---|---|---|
| UPCitemdb | 100 free/day | Return empty result for this source; do not abort |
| Open Products Facts | None stated | Return empty result on timeout (5s timeout) |
| Both services down | — | Return status = "unresolved" |

- Never throw an exception to the caller — always return a structured result.
- Log all responses (status code + response size) to `.tmp/ean_lookup.log`.

---

## Edge Cases

| Situation | Behaviour |
|---|---|
| EAN is 8 digits (EAN-8) | Validate and attempt — some products use EAN-8 |
| EAN has leading zeros | Preserve them — do not strip |
| UPCitemdb returns LEGO item with no set number in name | Return brand="LEGO", set_number=null, status="ambiguous"; user confirms |
| Cache hit with stale data | Cache never expires automatically — user can clear via settings in a future iteration |
