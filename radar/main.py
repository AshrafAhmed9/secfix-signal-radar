"""Daily run: ingest -> domains -> enrich -> score -> HubSpot -> Slack.

    python -m radar.main [--dry-run] [--limit N] [--stage ingest|all]
"""
import argparse
import json
import sys
from datetime import date

import anthropic

from radar import alerts, brief, config, crm, db, domain, enrich, http, ingest, llm, route, score
from radar.log import log
from radar.normalize import looks_like_agency, merge_by_domain, normalize_name

# Failures of one account or one call must never crash the whole run.
RECOVERABLE = (http.RequestFailed, enrich.EnrichmentFailed, anthropic.APIError,
               llm.LLMRefused, llm.LLMBadOutput, json.JSONDecodeError)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("--dry-run", action="store_true", help="no HubSpot or Slack writes; prints the digest")
    parser.add_argument("--limit", type=int, default=0, help="cap companies processed (cost control)")
    parser.add_argument("--stage", choices=["ingest", "all"], default="all",
                        help="'ingest' only fetches and prints per-source counts")
    return parser.parse_args(argv)


def require_keys(args) -> None:
    needed = [("ADZUNA_APP_ID", config.ADZUNA_APP_ID if "adzuna" in config.SOURCES else "x")]
    if args.stage == "all":
        needed.append(("HUBSPOT_TOKEN", config.HUBSPOT_TOKEN) if not args.dry_run else ("", "x"))
    missing = [name for name, value in needed if not value]
    if args.stage == "all":
        missing += llm.missing_settings()
    if missing:
        raise RuntimeError("missing settings: " + ", ".join(missing) + " (see .env.example)")


def run(conn, args, c: dict, state: dict) -> None:
    require_keys(args)

    state["stage"] = "ingest"
    postings, stats = ingest.fetch_postings(config.SOURCES, config.QUERIES, config.MAX_PAGES)
    c["failed"] += stats["failed"]
    c["fetched"] = sum(stats["raw"].values())
    log("ingest", "done", raw_by_source=stats["raw"], security_roles=len(postings), skipped_not_security=stats["irrelevant"])
    if args.stage == "ingest":
        for name, count in stats["raw"].items():
            print(f"{name}: {count} postings matched the queries")
        print(f"{len(postings)} have a security-role title; {stats['failed']} source calls failed")
        return

    client = llm.get_client()

    # Only postings we have not decided on before. Agencies are decided right away.
    fresh = [p for p in postings if not db.is_seen(conn, p["source"], p["posting_id"])]
    for p in [p for p in fresh if looks_like_agency(p["company_name"])]:
        db.mark_seen(conn, p["source"], p["posting_id"])
    fresh = [p for p in fresh if not looks_like_agency(p["company_name"])]

    by_company: dict[str, list[dict]] = {}
    for p in fresh:
        by_company.setdefault(normalize_name(p["company_name"]), []).append(p)
    companies = sorted(by_company.items(), key=lambda kv: -len(kv[1]))  # most signals first
    if args.limit:
        companies = companies[: args.limit]  # the rest stay unseen and are picked up on the next run

    state["stage"] = "domain"
    errored: set[str] = set()
    for normalized, plist in companies:
        try:
            found, cost = domain.resolve_domain(conn, client, plist[0]["company_name"],
                                                plist[0]["location"], config.model_for("extract"))
        except RECOVERABLE as exc:
            errored.add(normalized)  # not marked seen, so tomorrow retries it
            c["failed"] += 1
            log("domain", "lookup failed", company=plist[0]["company_name"], error=str(exc))
            continue
        c["cost"] += cost
        for p in plist:
            p["domain"] = found

    state["stage"] = "persist"
    decided = [p for normalized, plist in companies if normalized not in errored for p in plist]
    for account in merge_by_domain(decided):
        db.upsert_account(conn, account["domain"], account["company_name"], account["normalized_name"])
        for signal in account["signals"]:
            db.add_signal(conn, account["domain"], signal)
    for p in decided:  # merged, agency or unresolvable: all decided
        db.mark_seen(conn, p["source"], p["posting_id"])

    # Everything still waiting for a CRM sync: today's new accounts, accounts with a new posting,
    # and anything that failed earlier.
    work = db.pending_domains(conn)
    if args.limit:
        work = work[: args.limit]

    state["stage"] = "enrich+score"
    scored = []
    for domain_name in work:
        account = db.load_account(conn, domain_name)
        enrichment, status = None, "synced"
        try:
            enrichment, cost = enrich.enrich(conn, client, domain_name, account["company_name"])
            c["cost"] += cost
        except RECOVERABLE as exc:
            status = "enrichment_failed"  # still scored on postings alone; retried next run
            c["failed"] += 1
            log("enrich", "enrichment_failed", domain=domain_name, error=str(exc))
        result = score.score_account(account, enrichment)
        segment = route.segment_for(enrichment["employee_band"]) if enrichment else None
        scored.append({**account, "enrichment": enrichment, "result": result, "segment": segment,
                       "status": status, "brief": None, "hubspot_id": None})
    scored.sort(key=lambda a: a["result"]["score"], reverse=True)

    state["stage"] = "brief"
    for a in scored[: config.TOP_N_BRIEF]:  # briefs only for the accounts a rep will actually open
        try:
            a["brief"], cost = brief.make_brief(client, a, a["enrichment"], a["result"])
            c["cost"] += cost
        except RECOVERABLE as exc:
            c["failed"] += 1
            log("brief", "brief failed", domain=a["domain"], error=str(exc))

    state["stage"] = "crm"
    if not args.dry_run:
        crm.ensure_properties(config.HUBSPOT_TOKEN)
        owner_counts: dict = {}
        today = date.today().isoformat()
        for a in scored:
            owner = route.pick_owner(a["segment"], owner_counts)
            try:
                hubspot_id, action = crm.upsert_company(
                    a, a["result"], token=config.HUBSPOT_TOKEN, owner_id=owner,
                    segment=a["segment"], brief=a["brief"], today=today)
            except http.RequestFailed as exc:
                c["failed"] += 1
                db.save_result(conn, a["domain"], score=a["result"]["score"], reasons=a["result"]["reasons"], status="failed")
                log("crm", "upsert failed", domain=a["domain"], error=str(exc))
                continue
            a["hubspot_id"] = hubspot_id
            c["new_accounts" if action == "created" else "updated"] += 1
            db.save_result(conn, a["domain"], score=a["result"]["score"], reasons=a["result"]["reasons"],
                           status=a["status"], hubspot_id=hubspot_id)
            log("crm", action, domain=a["domain"], score=a["result"]["score"], hubspot_id=hubspot_id)
        scored = [a for a in scored if a["hubspot_id"]]  # only synced accounts are worth a rep's time

    state["stage"] = "alert"
    top = [{"company_name": a["company_name"], "domain": a["domain"], "score": a["result"]["score"],
            "reasons": a["result"]["reasons"], "segment": a["segment"], "hubspot_id": a["hubspot_id"]}
           for a in scored[: config.TOP_N_ALERT]]
    digest = alerts.build_digest(top, config.HUBSPOT_PORTAL_ID)
    if args.dry_run:
        print(digest)
    elif config.SLACK_DIGEST_WEBHOOK and top:
        alerts.post_slack(config.SLACK_DIGEST_WEBHOOK, digest)
        for a in top:
            db.log_alert(conn, a["domain"])
    else:
        log("alert", "digest not posted", reason="no webhook or no accounts", accounts=len(top))


def main(argv=None) -> int:
    args = parse_args(argv)
    conn = db.connect(config.DB_PATH)
    run_id = db.start_run(conn)
    c = {"fetched": 0, "new_accounts": 0, "updated": 0, "failed": 0, "cost": 0.0}
    state = {"stage": "start"}
    exit_code = 0
    try:
        run(conn, args, c, state)
        if c["failed"] and not args.dry_run and config.SLACK_ERROR_WEBHOOK:
            alerts.post_failure(config.SLACK_ERROR_WEBHOOK, "run",
                                f"{c['failed']} step(s) failed; the rest completed. See the run log.", run_id)
    except Exception as exc:  # a stage crashed: record it, alert, exit non-zero
        exit_code = 1
        c["failed"] += 1
        log(state["stage"], "stage crashed", error=f"{type(exc).__name__}: {exc}", run_id=run_id)
        if not args.dry_run and config.SLACK_ERROR_WEBHOOK:
            try:
                alerts.post_failure(config.SLACK_ERROR_WEBHOOK, state["stage"], f"{type(exc).__name__}: {exc}", run_id)
            except http.RequestFailed:
                log("alert", "could not post the failure alert", run_id=run_id)
    finally:
        db.finish_run(conn, run_id, fetched=c["fetched"], new_accounts=c["new_accounts"],
                      updated=c["updated"], failed=c["failed"], est_cost_usd=round(c["cost"], 4))
        log("run", "finished", run_id=run_id, **{k: (round(v, 4) if k == "cost" else v) for k, v in c.items()})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
