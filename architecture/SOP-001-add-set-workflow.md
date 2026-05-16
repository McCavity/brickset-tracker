# SOP-001 — Add Set Workflow

**Layer:** Navigation (orchestration)
**Goal:** Accept a new set from the user (via EAN scan or manual entry), fetch details, validate completeness, and persist the record to SQLite.

---

## Entry Points

| Entry point | When used |
|---|---|
| EAN scan / barcode input | User has physical set, scans barcode or types EAN |
| Manual entry | User knows brand + set number; MOCs; EAN lookup failed |

---

## Flow 1 — Set Number Known

```
Input: brand (string) + set_number (string)
  │
  ├─► SOP-003: scrape merlinssteine.de
  │     ├─ Success → pre-fill form with scraped data
  │     ├─ 404     → show "not found" notice, keep manual form open
  │     └─ Rate limit reached → skip scrape, keep manual form open
  │
  ├─► If brand is "LEGO" (case-insensitive):
  │     └─► SOP-004: Brickset getSets → merge any missing fields
  │
  └─► Present pre-filled form to user → go to Validate & Save
```

## Flow 2 — EAN Only

```
Input: EAN string (13-digit)
  │
  ├─► Check local EAN cache (ean_cache table)
  │     └─ Cache hit → extract brand + set_number → hand to Flow 1
  │
  ├─► (Cache miss) SOP-002: EAN resolution (UPCitemdb + Open Products Facts)
  │     ├─ Resolved → confirm brand + set_number with user → hand to Flow 1
  │     ├─ Ambiguous → present options list → user selects → hand to Flow 1
  │     └─ Unresolved → prompt manual brand + set_number entry → Flow 1
  │
  └─► Store resolved EAN ↔ (brand, set_number) in ean_cache
```

---

## Validate & Save

```
User reviews/edits pre-filled form
  │
  ├─► Required fields present? (brand, set_number, name, part_count)
  │     ├─ Yes → status = 'complete'
  │     └─ No  → offer: [Fix now] [Save as draft] [Cancel]
  │                         │              │           │
  │                      return        status =    discard,
  │                      to form       'draft'     navigate away
  │
  ├─► Duplicate check: any existing record with same (brand, set_number)?
  │     └─ Yes → show warning with count + list of existing copies
  │               User confirms to proceed (or cancels)
  │
  ├─► Save record to DB (status = 'complete' or 'draft')
  │     └─ Assign set_id
  │
  ├─► SOP-005: move staged photos from uploads/staging/{uuid}/ to uploads/{set_id}/
  │
  └─► If status = 'complete' AND brand = 'LEGO':
        └─ Offer "Sync to Brickset" button → SOP-004 setCollection
```

---

## Edge Cases

| Situation | Behaviour |
|---|---|
| Rate limit reached during Flow 1 scrape | Skip scrape silently, open blank manual form with brand+set_number pre-filled |
| merlinssteine.de returns 404 | Show "Set not found on merlinssteine.de" notice; keep form open for manual entry |
| merlinssteine.de returns ambiguous results | Not possible (URL-based lookup is deterministic); N/A |
| Network error during scrape | Treat as 404 — show notice, fall through to manual |
| User cancels mid-flow with staged photos | Staged folder stays in uploads/staging/; cleaned on next startup |
| All required fields entered but EAN unknown | Save without EAN; EAN field stays null |
| Duplicate confirmed and saved | PK auto-increment ensures distinct record; note field highlighted as differentiator |
