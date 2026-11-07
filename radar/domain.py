"""Find a company's website domain, and verify it before trusting it."""
import re

from radar import db, http, llm
from radar.log import log
from radar.normalize import clean_domain, normalize_name

NOT_A_COMPANY_SITE = ("linkedin.", "xing.", "indeed.", "stepstone.", "kununu.", "facebook.", "instagram.",
                      "adzuna.", "arbeitsagentur.", "wikipedia.", "glassdoor.", "northdata.", "google.")

SCHEMA = {
    "type": "object",
    "properties": {"domain": {"type": ["string", "null"]}},
    "required": ["domain"],
    "additionalProperties": False,
}


def name_in_page(normalized_name: str, page_text: str) -> bool:
    """Guard against a confident wrong answer: the page must mention the company's first word."""
    first_word = normalized_name.split()[0] if normalized_name.split() else ""
    return len(first_word) >= 3 and first_word in page_text.lower()


def verify(domain: str, normalized_name: str) -> bool:
    try:
        response = http.request("GET", f"https://{domain}", max_attempts=2, timeout=8.0,
                                headers={"User-Agent": "secfix-signal-radar/0.1"})
    except http.RequestFailed:
        return False
    return name_in_page(normalized_name, response.text)


def resolve_domain(conn, client, company_name: str, location: str, model: str) -> tuple[str | None, float]:
    """Return (domain or None, cost). Cached by normalised name, misses included."""
    normalized = normalize_name(company_name)
    cached, domain = db.get_cached_domain(conn, normalized)
    if cached:
        return domain, 0.0
    guess, cost = llm.ask_json(
        client, model,
        system="You give the official website domain of a company. Answer null when you are not sure; "
               "a wrong domain is worse than none.",
        prompt=f"Company: {company_name}\nLocation: {location or 'Germany, Austria or Switzerland'}\n"
               "What is the company's own website domain (like example.de, no https://, no path)?",
        schema=SCHEMA, max_tokens=1500)
    candidate = re.sub(r"^https?://", "", (guess.get("domain") or "").strip().lower()).split("/")[0]
    candidate = clean_domain(candidate)  # after the scheme is gone, so "https://www.x.de" loses its www too
    ok = bool(candidate) and "." in candidate and not any(w in candidate for w in NOT_A_COMPANY_SITE) \
        and verify(candidate, normalized)
    db.put_cached_domain(conn, normalized, candidate if ok else None)
    log("domain", "resolved" if ok else "unresolved", company=company_name, domain=candidate or None)
    return (candidate if ok else None), cost
