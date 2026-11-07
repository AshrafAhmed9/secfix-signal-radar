import json

import pytest

from radar import alerts, config, crm, db, enrich, http, main

POSTING = {"posting_id": "1", "source": "adzuna", "company_name": "Acme GmbH", "title": "ISMS Manager",
           "location": "Berlin", "created": "2026-11-01T00:00:00Z", "url": "https://x/1", "query": "ISMS"}
ENRICHMENT = {"industry": "Software", "employee_band": "50-249", "is_automotive_supplier": False,
              "sells_b2b": True, "already_certified": [], "nis2_sector": "none", "evidence": "x",
              "uses_competitor": False}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Everything external is faked; returns the lists the fakes record into."""
    rec = {"slack": [], "errors": [], "upserts": []}
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(config, "HUBSPOT_TOKEN", "t")
    monkeypatch.setattr(config, "SLACK_DIGEST_WEBHOOK", "https://hooks/digest")
    monkeypatch.setattr(config, "SLACK_ERROR_WEBHOOK", "https://hooks/errors")
    monkeypatch.setattr(main.llm, "get_client", lambda: object())
    monkeypatch.setattr(main.ingest, "fetch_postings",
                        lambda *a, **k: ([dict(POSTING)], {"failed": 0, "raw": {"adzuna": 1}, "irrelevant": 0}))
    monkeypatch.setattr(main.domain, "resolve_domain", lambda *a, **k: ("acme.de", 0.001))
    monkeypatch.setattr(main.enrich, "enrich", lambda *a, **k: (dict(ENRICHMENT), 0.002))
    monkeypatch.setattr(main.brief, "make_brief", lambda *a, **k: ("- Why now: x", 0.01))
    monkeypatch.setattr(crm, "ensure_properties", lambda token: [])

    def upsert(account, result, **kw):
        rec["upserts"].append((account["domain"], result["score"], kw["segment"], kw["brief"]))
        return "42", "created"

    monkeypatch.setattr(crm, "upsert_company", upsert)
    monkeypatch.setattr(alerts, "post_slack", lambda hook, text: rec["slack"].append(text))
    monkeypatch.setattr(alerts, "post_failure", lambda hook, stage, err, run_id: rec["errors"].append((stage, err)))
    return rec


def last_run(tmp_path):
    conn = db.connect(str(tmp_path / "t.db"))
    return dict(conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone())


def test_full_run_syncs_scores_routes_and_posts_the_digest(env, tmp_path):
    assert main.main([]) == 0
    domain, score, segment, brief_text = env["upserts"][0]
    assert (domain, segment, brief_text) == ("acme.de", "SMB", "- Why now: x")
    assert score == 30 + 15 + 15  # hiring + sells B2B + 50-249 employees
    assert len(env["slack"]) == 1 and "acme.de" in env["slack"][0]
    run = last_run(tmp_path)
    assert run["new_accounts"] == 1 and run["failed"] == 0 and run["finished_at"]
    assert run["est_cost_usd"] > 0 and env["errors"] == []


def test_second_run_the_same_day_changes_nothing(env, tmp_path):
    main.main([])
    env["upserts"].clear()
    env["slack"].clear()
    assert main.main([]) == 0
    assert env["upserts"] == [] and env["slack"] == []
    run = last_run(tmp_path)
    assert run["new_accounts"] == 0 and run["updated"] == 0


def test_dry_run_writes_nothing_external_and_prints_the_digest(env, capsys):
    assert main.main(["--dry-run"]) == 0
    assert env["upserts"] == [] and env["slack"] == []
    assert "acme.de" in capsys.readouterr().out


def test_dry_run_leaves_the_account_pending_for_the_real_run(env):
    main.main(["--dry-run"])
    assert main.main([]) == 0
    assert len(env["upserts"]) == 1  # the real run still picks it up


def test_crm_failure_is_alerted_and_retried_next_run(env, monkeypatch, tmp_path):
    def failing(account, result, **kw):
        raise http.RequestFailed("HubSpot down", 500)

    monkeypatch.setattr(crm, "upsert_company", failing)
    assert main.main([]) == 0
    assert last_run(tmp_path)["failed"] == 1
    assert env["errors"] and env["errors"][0][0] == "run"
    assert env["slack"] == []  # nothing synced, so nothing for reps
    monkeypatch.setattr(crm, "upsert_company", lambda account, result, **kw: ("7", "created"))
    assert main.main([]) == 0
    assert last_run(tmp_path)["new_accounts"] == 1  # the failed account was retried


def test_enrichment_failure_still_scores_on_postings(env, monkeypatch):
    def failing(*a, **k):
        raise enrich.EnrichmentFailed("site down")

    monkeypatch.setattr(main.enrich, "enrich", failing)
    assert main.main([]) == 0
    assert env["upserts"][0][1] == 30  # hiring rule only


def test_a_crashing_stage_alerts_with_the_stage_name_and_exits_nonzero(env, monkeypatch, tmp_path):
    def crash(*a, **k):
        raise ValueError("kaboom")

    monkeypatch.setattr(main.ingest, "fetch_postings", crash)
    assert main.main([]) == 1
    assert env["errors"] == [("ingest", "ValueError: kaboom")]
    assert last_run(tmp_path)["failed"] == 1


def test_missing_keys_fail_before_any_work(env, monkeypatch):
    monkeypatch.setattr(config, "HUBSPOT_TOKEN", "")
    assert main.main([]) == 1
    assert "HUBSPOT_TOKEN" in env["errors"][0][1]


def test_stage_ingest_only_prints_counts(env, capsys):
    assert main.main(["--stage", "ingest"]) == 0
    out = capsys.readouterr().out
    assert "adzuna: 1 postings" in out and env["upserts"] == []
