# CLAUDE.md — Project Constitution: brickset-tracker

## North Star
Scan or manually enter an EAN → fetch set details from the internet (or fill in manually) → record is saved successfully to the local SQLite database.

---

## Data Schema

### Input Shape (Add Set)
```json
{
  "ean":             "string | null",
  "brand":           "string",          // REQUIRED
  "set_number":      "string",          // REQUIRED — brand-internal number
  "name":            "string",          // REQUIRED
  "part_count":      "integer",         // REQUIRED
  "condition":       "enum | null",
  "location":        "string | null",
  "date_of_purchase":"date | null",     // default: NOW()
  "note":            "string | null",
  "theme":           "string | null",
  "release_year":    "integer | null",
  "images":          "string[] | null", // mix of URLs and local file paths
  "minifigs":        "integer | null",
  "price_paid":      "decimal | null",
  "status":          "enum"             // 'complete' | 'draft'
}
```

### Output Shape (Database Record)
```json
{
  "id":              "integer",         // PK, auto-increment
  "ean":             "string | null",
  "brand":           "string",
  "set_number":      "string",
  "name":            "string",
  "part_count":      "integer",
  "condition":       "string | null",
  "location":        "string | null",
  "date_of_purchase":"date",
  "note":            "string | null",
  "theme":           "string | null",
  "release_year":    "integer | null",
  "images":          "text | null",     // JSON array serialized as text
  "minifigs":        "integer | null",
  "price_paid":      "real | null",
  "status":          "text",            // 'complete' | 'draft'
  "created_at":      "timestamp",
  "updated_at":      "timestamp"
}
```

### Condition Enum (German, emoji-prefixed)
| Value | Meaning |
|---|---|
| `📦 OVP — gekauft, ungeöffnet` | New, sealed |
| `🔨 Im Bau — angefangen, liegt irgendwo` | Build in progress |
| `✅ Gebaut — fertig, steht/liegt` | Built and displayed |
| `📥 Abgebaut — wieder zerlegt, in Kisten oder Tüten` | Disassembled |
| `💸 Verkauft — nicht mehr vorhanden` | Sold, no longer owned |

### Record Completeness
A record is **complete** when all four required fields are present: `brand`, `set_number`, `name`, `part_count`.
Everything else is optional. Missing required fields → status = `'draft'`.

---

## Behavioral Rules

1. **Unrecognized EAN**: prompt user to fill mandatory fields manually → save as draft or cancel.
2. **Ambiguous lookup results**: always present options to the user — never auto-select.
3. **Incomplete record**: offer save-as-draft or cancel. Never silently discard data.
4. **Duplicates**: permitted. Same EAN/set can exist multiple times (e.g. two builds of the same Creator 3in1 set). Primary key is the sole distinction; user uses `note` field to differentiate.
5. **Delete**: always require a confirmation dialog. Never delete silently.
6. **Photos**: never auto-overwrite an existing photo. Always prompt or append.
7. **Language**: bilingual — German primary (`de`), English secondary (`en`). i18n built in from day one. Language switchable via UI.

---

## Architectural Invariants

- All business logic lives in `/execution/` as deterministic, atomic scripts.
- All routing/decision logic lives in the Navigation layer.
- All SOPs live in `/architecture/` — if logic changes, update the SOP first, then the code.
- Credentials and API keys live in `.env` — never hardcoded.
- Temporary files (scraped data, drafts, logs) go in `/.tmp/`.
- Own uploaded photos go in `/uploads/` (never overwritten, only appended).

---

## B.L.A.S.T. Phase Outputs

| Phase | Status | Key Decisions |
|---|---|---|
| **B — Blueprint** | ✅ Complete | Data schema defined; iteration plan set |
| **L — Link** | ✅ Complete | Brickset API verified; userHash in .env; generic EAN DBs confirmed non-viable for bricks |
| **A — Architect** | ✅ Complete | 8 SOPs written; A.N.T. layers created; skeleton files in place |
| **S — Stylize** | ⏳ Pending | List-first UI; bilingual i18n |
| **T — Trigger** | ⏳ Pending | Local server startup command TBD |

---

## Iteration Plan

| Iteration | Scope |
|---|---|
| 1 — MVP | Add set (EAN lookup + manual fallback), list view with sorting, duplicate detection & allow |
| 2 | Edit + delete records (with confirmation dialogs) |
| 3 | Search + filter |
| Later | Card grid, stats dashboard |

---

## Trigger / Startup

_To be documented after Phase T._

---

## Maintenance Log

_Populated during Phase T._
