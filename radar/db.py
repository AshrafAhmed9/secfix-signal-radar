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


# --- accounts and signals -------------------------------------------------------------

# Accounts in these states still need a CRM sync. 'synced' ones come back only on a new posting.
PENDING_STATUSES = ("new", "pending", "failed", "enrichment_failed")


def upsert_account(conn: sqlite3.Connection, domain: str, name: str, normalized_name: str) -> None:
    conn.execute(
        "INSERT INTO accounts (domain, name, normalized_name, first_seen, last_seen) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(domain) DO UPDATE SET last_seen = excluded.last_seen",
        (domain, name, normalized_name, now(), now()),
    )
    conn.commit()


def add_signal(conn: sqlite3.Connection, domain: str, posting: dict) -> bool:
    """Store a posting as a signal. True if it was new. A new signal re-opens a synced account."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO signals (source, posting_id, domain, title, location, created, url, query) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (posting["source"], posting["posting_id"], domain, posting["title"], posting["location"],
         posting["created"], posting["url"], posting["query"]),
    )
    is_new = cur.rowcount == 1
    if is_new:
        conn.execute("UPDATE accounts SET status = 'pending' WHERE domain = ? AND status = 'synced'", (domain,))
    conn.commit()
    return is_new


def pending_domains(conn: sqlite3.Connection) -> list[str]:
    marks = ",".join("?" * len(PENDING_STATUSES))
    rows = conn.execute(f"SELECT domain FROM accounts WHERE status IN ({marks}) ORDER BY first_seen",
                        PENDING_STATUSES).fetchall()
    return [r["domain"] for r in rows]


def load_account(conn: sqlite3.Connection, domain: str) -> dict:
    """Account dict (as merge_by_domain builds it) from everything stored for this domain."""
    row = conn.execute("SELECT name, normalized_name FROM accounts WHERE domain = ?", (domain,)).fetchone()
    signals = [dict(r) | {"company_name": row["name"]} for r in conn.execute(
        "SELECT source, posting_id, title, location, created, url, query FROM signals "
        "WHERE domain = ? ORDER BY created DESC, posting_id", (domain,))]
    return {"domain": domain, "company_name": row["name"], "normalized_name": row["normalized_name"],
            "signals": signals, "sources": sorted({s["source"] for s in signals})}


def save_result(conn: sqlite3.Connection, domain: str, *, score: int, reasons: list[str],
                status: str, hubspot_id: str | None = None) -> None:
    conn.execute(
        "UPDATE accounts SET score = ?, reasons = ?, status = ?, hubspot_id = COALESCE(?, hubspot_id) "
        "WHERE domain = ?", (score, "\n".join(reasons), status, hubspot_id, domain))
    conn.commit()


def log_alert(conn: sqlite3.Connection, domain: str) -> None:
    conn.execute("INSERT INTO alerts (domain, alerted_at) VALUES (?, ?)", (domain, now()))
    conn.commit()


# --- caches ---------------------------------------------------------------------------

def get_cached_domain(conn: sqlite3.Connection, normalized_name: str) -> tuple[bool, str | None]:
    """(was_cached, domain). A cached miss is (True, None): we don't retry unresolvable names daily."""
    row = conn.execute("SELECT domain FROM domain_cache WHERE normalized_name = ?", (normalized_name,)).fetchone()
    return (row is not None, row["domain"] if row else None)


def put_cached_domain(conn: sqlite3.Connection, normalized_name: str, domain: str | None) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO domain_cache (normalized_name, domain, verified, checked_at) VALUES (?, ?, ?, ?)",
        (normalized_name, domain, 1 if domain else 0, now()))
    conn.commit()


def get_cached_enrichment(conn: sqlite3.Connection, domain: str) -> dict | None:
    import json
    row = conn.execute("SELECT result_json FROM enrichment_cache WHERE domain = ?", (domain,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def put_cached_enrichment(conn: sqlite3.Connection, domain: str, result: dict) -> None:
    import json
    conn.execute("INSERT OR REPLACE INTO enrichment_cache (domain, result_json, fetched_at) VALUES (?, ?, ?)",
                 (domain, json.dumps(result), now()))
    conn.commit()
