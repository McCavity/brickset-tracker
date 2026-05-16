"""
Database initialisation and connection management.
See architecture/SOP-008-database.md for schema and query patterns.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/brickset.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sets (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ean              TEXT,
                brand            TEXT    NOT NULL,
                set_number       TEXT    NOT NULL,
                name             TEXT    NOT NULL,
                part_count       INTEGER NOT NULL,
                condition        TEXT,
                location         TEXT,
                date_of_purchase TEXT,
                note             TEXT,
                theme            TEXT,
                release_year     INTEGER,
                web_images       TEXT,
                own_photos       TEXT,
                minifigs         INTEGER,
                price_paid       REAL,
                brickset_set_id  INTEGER,
                status           TEXT    NOT NULL DEFAULT 'draft',
                created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ean_cache (
                ean          TEXT PRIMARY KEY,
                brand        TEXT NOT NULL,
                set_number   TEXT NOT NULL,
                source       TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS scrape_quota (
                service      TEXT NOT NULL,
                date         TEXT NOT NULL,
                count        INTEGER DEFAULT 0,
                PRIMARY KEY (service, date)
            );

            CREATE INDEX IF NOT EXISTS idx_sets_brand  ON sets(brand);
            CREATE INDEX IF NOT EXISTS idx_sets_date   ON sets(date_of_purchase);
            CREATE INDEX IF NOT EXISTS idx_sets_status ON sets(status);
        """)
