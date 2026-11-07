"""Stage 7: a short research brief for the rep. Claude researches; the rep writes the message."""
from radar import config, llm

ROLES = ["CTO", "CISO", "CIO", "Head of IT", "COO", "CEO / Geschäftsführer"]

SCHEMA = {
    "type": "object",
    "properties": {
        "why_now": {"type": "string"},
        "likely_pain": {"type": "string"},
        "frameworks": {"type": "array", "items": {"type": "string", "enum": ["ISO 27001", "TISAX", "SOC 2", "NIS2"]}},
        "roles_to_approach": {"type": "array", "items": {"type": "string", "enum": ROLES}},
    },
    "required": ["why_now", "likely_pain", "frameworks", "roles_to_approach"],
    "additionalProperties": False,
}

SYSTEM = (
    "You prepare a short research brief for a sales rep at a compliance-automation company. "
    "Use only the facts given. Do not invent people, numbers or news. "
    "Do not write outreach messages or email copy: the rep writes their own words. "
    "Each field is one or two plain sentences."
)


def make_brief(client, account: dict, enrichment: dict | None, result: dict) -> tuple[str, float]:
    """Return (brief text, cost). Evidence links come from our own data, never from the model."""
    postings = "\n".join(f"- {s['title']} ({s['location']}, {s['created'][:10]})" for s in account["signals"][:5])
    facts = enrichment or {}
    prompt = (
        f"Company: {account['company_name']} ({account['domain']})\n"
        f"Open security-related postings:\n{postings}\n"
        f"Industry: {facts.get('industry', 'unknown')}; size: {facts.get('employee_band', 'unknown')}; "
        f"automotive supplier: {facts.get('is_automotive_supplier', 'unknown')}; "
        f"already certified: {facts.get('already_certified', 'unknown')}; NIS2 sector: {facts.get('nis2_sector', 'unknown')}\n"
        f"Why it scored {result['score']}: {'; '.join(result['reasons'])}"
    )
    data, cost = llm.ask_json(client, config.MODEL_BRIEF, SYSTEM, prompt, SCHEMA, max_tokens=4000)
    evidence = ", ".join(s["url"] for s in account["signals"][:3] if s["url"])
    text = "\n".join([
        f"- Why now: {data['why_now']}",
        f"- Likely pain: {data['likely_pain']}",
        f"- Framework: {', '.join(data['frameworks']) or 'to confirm on the call'}",
        f"- Who to approach: {', '.join(data['roles_to_approach']) or 'to confirm'}",
        f"- Evidence: {evidence}",
    ])
    return text, cost
