"""Find a company's website domain, and verify it before trusting it."""
import re
from urllib.parse import urlparse

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


def verify(domain: str, normalized_name: str, strict: bool = False) -> str | None:
    """Fetch the site. Returns its canonical domain (after redirects) if the page names the company.

    The canonical domain is the key, so "schwarzdigits.com" and "schwarz-digits.com", which both
    redirect to schwarz-digits.de, end up as ONE account instead of two CRM records.
    """
    try:
        response = http.request("GET", f"https://{domain}", max_attempts=2, timeout=8.0,
                                headers={"User-Agent": "secfix-signal-radar/0.1"})
    except http.RequestFailed:
        return None
    if not name_in_page(normalized_name, response.text, strict):
        return None
    final = clean_domain(urlparse(response.url).netloc.split(":")[0])
    return final or domain


def resolve_domain(conn, client, company_name: str, location: str, model: str) -> tuple[str | None, float]:
    """Return (domain or None, cost). Cached by normalised name, misses included."""
    normalized = normalize_name(company_name)
    cached, domain = db.get_cached_domain(conn, normalized)
    if cached:
        return domain, 0.0
    for candidate in guess_candidates(normalized):  # free check first
        canonical = verify(candidate, normalized, strict=True)
        if canonical and not any(w in canonical for w in NOT_A_COMPANY_SITE):
            db.put_cached_domain(conn, normalized, canonical)
            log("domain", "resolved", company=company_name, domain=canonical, how="guess")
            return canonical, 0.0
    guess, cost = llm.ask_json(
        client, model,
        system="You give the official website domain of a company. Answer null when you are not sure; "
               "a wrong domain is worse than none.",
        prompt=f"Company: {company_name}\nLocation: {location or 'Germany, Austria or Switzerland'}\n"
               "What is the company's own website domain (like example.de, no https://, no path)?",
        schema=SCHEMA, max_tokens=1500)
    candidate = re.sub(r"^https?://", "", (guess.get("domain") or "").strip().lower()).split("/")[0]
    candidate = clean_domain(candidate)  # after the scheme is gone, so "https://www.x.de" loses its www too
    plausible = "." in candidate and not any(w in candidate for w in NOT_A_COMPANY_SITE)
    canonical = verify(candidate, normalized) if plausible else None
    if canonical and any(w in canonical for w in NOT_A_COMPANY_SITE):
        canonical = None
    db.put_cached_domain(conn, normalized, canonical)
    log("domain", "resolved" if canonical else "unresolved", company=company_name, domain=canonical or candidate or None)
    return canonical, cost
