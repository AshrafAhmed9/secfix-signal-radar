"""Stage 6: the daily Slack digest and the failure alert."""
from radar import crm, http

SEGMENT_ORDER = ["Mid-Market", "SMB", None]


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_digest(accounts: list[dict], portal_id: str = "") -> str:
    """Top accounts to call today, grouped by segment. Each line: name, score, 2 strongest reasons, link.

    accounts: dicts with company_name, domain, score, reasons, segment, hubspot_id (optional).
    """
    if not accounts:
        return "No new accounts to call today."
    lines = [f"*Top {len(accounts)} accounts to call today*"]
    for segment in SEGMENT_ORDER:
        group = [a for a in accounts if a.get("segment") == segment]
        if not group:
            continue
        lines.append(f"\n*{segment or 'No segment'}*")
        for a in group:
            link = ""
            if portal_id and a.get("hubspot_id"):
                link = f" · <{crm.company_url(portal_id, a['hubspot_id'])}|HubSpot>"
            lines.append(f"• *{_escape(a['company_name'])}* ({_escape(a['domain'])}) · score {a['score']}{link}")
            for reason in a["reasons"][:2]:
                lines.append(f"    – {_escape(reason)}")
    return "\n".join(lines)


def post_slack(webhook: str, text: str) -> None:
    http.request("POST", webhook, json={"text": text})


def post_failure(webhook: str, stage: str, error: str, run_id: int) -> None:
    post_slack(webhook, f":rotating_light: *signal-radar failed* · stage `{stage}` · run #{run_id}\n{_escape(error)[:500]}")
