"""
Daily quota tracking for external services.
See architecture/SOP-006-rate-limit.md.
"""
from datetime import date
from execution.db import get_connection

LIMITS: dict[str, int] = {
    "merlinssteine": 10,
    "brickset": 100,
    "upcitemdb": 100,
}


def check_quota(service: str) -> bool:
    """Return True if quota is available, False if exhausted."""
    today = date.today().isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT count FROM scrape_quota WHERE service=? AND date=?",
            (service, today),
        ).fetchone()
    count = row["count"] if row else 0
    return count < LIMITS[service]


def increment_quota(service: str) -> None:
    """Increment the daily counter for a service."""
    today = date.today().isoformat()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO scrape_quota (service, date, count) VALUES (?, ?, 1)
               ON CONFLICT(service, date) DO UPDATE SET count = count + 1""",
            (service, today),
        )


def get_quota_status() -> dict:
    """Return current quota usage for all services."""
    today = date.today().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT service, count FROM scrape_quota WHERE date=?", (today,)
        ).fetchall()
    usage = {row["service"]: row["count"] for row in rows}
    return {
        svc: {
            "used": usage.get(svc, 0),
            "limit": limit,
            "remaining": limit - usage.get(svc, 0),
        }
        for svc, limit in LIMITS.items()
    }
