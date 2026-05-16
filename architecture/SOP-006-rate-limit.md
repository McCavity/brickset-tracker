# SOP-006 — Rate Limit Enforcement

**Layer:** Tool (execution)
**Goal:** Track and enforce daily request quotas for external services. Quotas reset at midnight local time. Prevents over-use of community resources.

---

## Quotas

| Service key | Daily limit | Resets |
|---|---|---|
| `merlinssteine` | 10 | Midnight local time |
| `brickset` | 100 | Midnight local time |
| `upcitemdb` | 100 | Midnight local time |

---

## Database Table

```sql
CREATE TABLE IF NOT EXISTS scrape_quota (
    service   TEXT NOT NULL,
    date      TEXT NOT NULL,        -- ISO date: "2026-05-15"
    count     INTEGER DEFAULT 0,
    PRIMARY KEY (service, date)
);
```

---

## Operations

### check_quota(service: str) → bool
```
1. Get today's date string (local time): date.today().isoformat()
2. SELECT count FROM scrape_quota WHERE service=? AND date=?
3. If no row found: count = 0
4. Return: count < LIMIT[service]
   ├─ True  → quota available
   └─ False → quota exhausted
```

### increment_quota(service: str) → None
```
1. Get today's date string.
2. INSERT INTO scrape_quota (service, date, count) VALUES (?, ?, 1)
   ON CONFLICT(service, date) DO UPDATE SET count = count + 1
```

### get_quota_status() → dict
```
Returns current counts for all services for today.
Used by the UI to show remaining quota to the user.
{
  "merlinssteine": {"used": 3, "limit": 10, "remaining": 7},
  "brickset":      {"used": 12, "limit": 100, "remaining": 88},
  "upcitemdb":     {"used": 0, "limit": 100, "remaining": 100}
}
```

---

## When to Increment

| Service | Increment on |
|---|---|
| merlinssteine | Every HTTP request that reaches the network (200, 404, 429) — NOT on connection errors |
| brickset | Every `getSets` call that reaches the network |
| upcitemdb | Every lookup call that reaches the network |

Connection errors (DNS failure, timeout, refused) do NOT consume quota.

---

## UI Exposure

- The remaining merlinssteine quota is always visible in the sidebar/header (e.g. "Merlinssteine: 7/10 heute").
- When quota is exhausted: banner shown, scrape button disabled, manual entry form offered automatically.
- No quota warnings for brickset or upcitemdb in MVP (limits are generous enough).
