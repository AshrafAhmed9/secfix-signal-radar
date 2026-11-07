"""SQLite with plain SQL. One connection per run."""
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    domain TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    score INTEGER,
    reasons TEXT,
    hubspot_id TEXT,
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE TABLE IF NOT EXISTS signals (
    source TEXT NOT NULL,
    posting_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT,
    location TEXT,
    created TEXT,
    url TEXT,
    query TEXT,
    PRIMARY KEY (source, posting_id)
);
CREATE TABLE IF NOT EXISTS seen_postings (
    source TEXT NOT NULL,
    posting_id TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (source, posting_id)
);
CREATE TABLE IF NOT EXISTS domain_cache (
    normalized_name TEXT PRIMARY KEY,
    domain TEXT,
    verified INTEGER NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrichment_cache (
    domain TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    domain TEXT NOT NULL,
    alerted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched INTEGER NOT NULL DEFAULT 0,
    new_accounts INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    est_cost_usd REAL NOT NULL DEFAULT 0
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def is_seen(conn: sqlite3.Connection, source: str, posting_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_postings WHERE source = ? AND posting_id = ?",
        (source, posting_id),
    ).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, source: str, posting_id: str) -> None:
    # OR IGNORE: marking twice is fine, that is what makes reruns idempotent.
    conn.execute(
        "INSERT OR IGNORE INTO seen_postings (source, posting_id, seen_at) VALUES (?, ?, ?)",
        (source, posting_id, now()),
    )
    conn.commit()


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, *, fetched: int, new_accounts: int,
               updated: int, failed: int, est_cost_usd: float) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, fetched = ?, new_accounts = ?, updated = ?, "
        "failed = ?, est_cost_usd = ? WHERE id = ?",
        (now(), fetched, new_accounts, updated, failed, est_cost_usd, run_id),
    )
    conn.commit()
