"""Precision of the ranking, from hand labels.

    python -m eval.precision make     # writes eval/labels.csv from the top accounts in radar.db
    python -m eval.precision report   # reads the filled-in labels, prints precision@5 and @10

Fill the `fit` column with y or n for each row, and a short `reason`. "Fit" means: would a Secfix
BDR be glad to call this company about ISO 27001, TISAX, NIS2 or SOC 2? Only labelled rows count.
"""
import csv
import sqlite3
import sys

from radar import config

LABELS = "eval/labels.csv"
FIELDS = ["rank", "domain", "name", "score", "fit", "reason"]


def top_accounts(db_path: str, n: int = 10) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT domain, name, score FROM accounts WHERE status IN ('synced', 'pending') "
        "ORDER BY score DESC, domain LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]


def make(db_path: str = config.DB_PATH, path: str = LABELS) -> None:
    rows = top_accounts(db_path)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, FIELDS)
        writer.writeheader()
        for rank, r in enumerate(rows, 1):
            writer.writerow({"rank": rank, **r, "fit": "", "reason": ""})
    print(f"wrote {len(rows)} rows to {path}: fill the fit column with y or n")


def precision_at(labels: list[dict], k: int) -> tuple[float, int] | None:
    """(precision, labelled_count) over the top-k ranks, or None if nothing in the top k is labelled."""
    top = [r for r in labels if int(r["rank"]) <= k and r["fit"].strip().lower() in ("y", "n")]
    if not top:
        return None
    good = sum(r["fit"].strip().lower() == "y" for r in top)
    return good / len(top), len(top)


def report(path: str = LABELS) -> None:
    with open(path, newline="") as f:
        labels = list(csv.DictReader(f))
    for k in (5, 10):
        result = precision_at(labels, k)
        if result is None:
            print(f"precision@{k}: no labelled rows yet")
        else:
            p, n = result
            print(f"precision@{k}: {p:.0%} ({round(p * n)} of {n} labelled)")
    misses = [r for r in labels if r["fit"].strip().lower() == "n"]
    if misses:
        print("\nfalse positives (what to fix):")
        for r in misses:
            print(f"  #{r['rank']} {r['name']} ({r['domain']}) score {r['score']}: {r['reason'] or 'no reason given'}")


if __name__ == "__main__":
    {"make": make, "report": report}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
