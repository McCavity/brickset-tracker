# SOP-004 — Brickset API Client

**Layer:** Tool (execution)
**Goal:** Two operations — (1) fetch LEGO set metadata by set number, (2) sync a set's owned status to the user's Brickset account.

---

## Credentials (from .env)
```
BRICKSET_API_KEY  — API key string
BRICKSET_USER_HASH — persistent session hash (no expiry)
```

## Daily Budget
`getSets` calls: **100/day** (free tier). Tracked separately from the merlinssteine.de quota.
`setCollection` calls: unlimited (no documented cap).

---

## Operation A — Fetch Set Metadata

### Input
```
set_number: string  — LEGO set number, e.g. "42172-1" or "42172"
```

### Output
```
{
  "status":       "found" | "not_found" | "quota_exceeded" | "error",
  "set_id":       integer | null,   # Brickset internal ID — required for sync
  "name":         string | null,
  "pieces":       integer | null,
  "theme":        string | null,
  "year":         integer | null,
  "ean":          string | null,
  "image_url":    string | null
}
```

### Steps
```
1. Check Brickset daily quota (tracked in scrape_quota table, key="brickset").
   └─ Quota exhausted → return status = "quota_exceeded"

2. POST to https://brickset.com/api/v3.asmx/getSets
   Body (form-encoded):
     apiKey   = BRICKSET_API_KEY
     userHash = BRICKSET_USER_HASH
     params   = {"setNumber": "{set_number}"}

3. Increment Brickset quota counter.

4. Parse response:
   ├─ status != "success"    → return status = "error"
   ├─ sets list empty        → try without variant suffix (e.g. "42172" if "42172-1" fails)
   ├─ sets list has 1 item   → extract fields, return status = "found"
   └─ sets list has >1 item  → present to user for selection (ambiguous)

5. Cache the resolved setID in the local sets record on first successful fetch.
```

---

## Operation B — Sync Owned Status

### Input
```
set_id:    integer  — Brickset internal setID (from Operation A)
qty_owned: integer  — count of complete (non-draft) records with same (brand, set_number) in local DB
```

### Steps
```
1. POST to https://brickset.com/api/v3.asmx/setCollection
   Body (form-encoded):
     apiKey   = BRICKSET_API_KEY
     userHash = BRICKSET_USER_HASH
     setID    = {set_id}
     params   = {"own": 1, "qtyOwned": {qty_owned}, "want": 0, "notes": ""}

2. Check response:
   ├─ status = "success" → confirm in UI
   └─ status = "error"   → show error message; do not retry automatically

3. Log sync event to .tmp/brickset_sync.log: timestamp, set_id, qty_owned, result.
```

---

## Edge Cases

| Situation | Behaviour |
|---|---|
| Set number has no variant suffix on Brickset | Try "42172-1" first, then "42172" if not found |
| getSets returns multiple sets (different years) | Present list to user; user selects correct one |
| userHash expired (unlikely — persistent) | Return status="error" with message; user must re-authenticate via settings |
| Daily quota (100) exhausted | Return status="quota_exceeded"; skip sync; show notice in UI |
| qty_owned includes draft records | Exclude drafts — only count records with status='complete' |
| Set is Alt Brick (non-LEGO) | Caller (SOP-001) never invokes Brickset for non-LEGO brands; this SOP is LEGO-only |
