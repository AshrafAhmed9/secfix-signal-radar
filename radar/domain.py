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


def name_in_page(normalized_name: str, page_text: str, strict: bool = False) -> bool:
    """Guard against a confident wrong answer: the page must mention the company's name.

    Lenient (for a domain the LLM named): the first word. Strict (for a domain we only guessed
    from the name): every word, because a guess has nothing else backing it.
    """
    words = normalized_name.split()
    if not words:
        return False
    text = page_text.lower()
    if strict:
        return len(normalized_name) >= 4 and all(w in text for w in words)
    return len(words[0]) >= 3 and words[0] in text


def guess_candidates(normalized_name: str) -> list[str]:
    """Domains a company name might map to, tried before spending an LLM call. Free and checkable."""
    words = normalized_name.split()
    if not words or len(words) > 3 or not normalized_name.isascii():
        return []
    bases = list(dict.fromkeys(["".join(words), "-".join(words)]))
    return [f"{base}.{tld}" for base in bases for tld in ("de", "com")]


def verify(domain: str, normalized_name: str, strict: bool = False) -> bool:
    try:
        response = http.request("GET", f"https://{domain}", max_attempts=2, timeout=8.0,
                                headers={"User-Agent": "secfix-signal-radar/0.1"})
    except http.RequestFailed:
        return False
    return name_in_page(normalized_name, response.text, strict)


def resolve_domain(conn, client, company_name: str, location: str, model: str) -> tuple[str | None, float]:
    """Return (domain or None, cost). Cached by normalised name, misses included."""
    normalized = normalize_name(company_name)
    cached, domain = db.get_cached_domain(conn, normalized)
    if cached:
        return domain, 0.0
    for candidate in guess_candidates(normalized):  # free check first
        if verify(candidate, normalized, strict=True):
            db.put_cached_domain(conn, normalized, candidate)
            log("domain", "resolved", company=company_name, domain=candidate, how="guess")
            return candidate, 0.0
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
