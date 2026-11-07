from radar import db


def test_marking_a_posting_seen_twice_is_harmless(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    assert not db.is_seen(conn, "adzuna", "1")
    db.mark_seen(conn, "adzuna", "1")
    db.mark_seen(conn, "adzuna", "1")
    assert db.is_seen(conn, "adzuna", "1")
    assert not db.is_seen(conn, "arbeitsagentur", "1")  # same id, other source


def test_run_row_is_written_and_finished(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    run_id = db.start_run(conn)
    db.finish_run(conn, run_id, fetched=10, new_accounts=3, updated=2, failed=0, est_cost_usd=0.12)
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["fetched"] == 10 and row["new_accounts"] == 3 and row["finished_at"]
