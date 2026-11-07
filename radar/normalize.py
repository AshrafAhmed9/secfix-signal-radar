"""Company-name normalisation and merging postings into accounts."""

# Token sequences stripped from the END of a name, longest first. Order matters:
# "co kg" has to be tried before "kg", or "foo co kg" would end up as "foo co".
LEGAL_SUFFIXES = [
    ["co", "kg"],
    ["ug", "haftungsbeschränkt"],
    ["gmbh"], ["ag"], ["se"], ["kg"], ["ug"], ["mbh"], ["inc"], ["ltd"],
]

AGENCY_KEYWORDS = ["personal", "recruiting", "consulting", "zeitarbeit", "staffing"]


def normalize_name(name: str) -> str:
    """Lowercase, punctuation to spaces, collapse whitespace, strip legal suffixes.

    "Müller GmbH & Co. KG" -> "müller". If stripping would leave nothing (a company
    literally called "SE"), keep the lowercased name instead.
    """
    tokens = "".join(c if c.isalnum() else " " for c in name.lower()).split()
    original = tokens[:]
    stripped = True
    while stripped and tokens:
        stripped = False
        for suffix in LEGAL_SUFFIXES:
            if len(tokens) >= len(suffix) and tokens[-len(suffix):] == suffix:
                tokens = tokens[:-len(suffix)]
                stripped = True
                break
    return " ".join(tokens or original)


def looks_like_agency(name: str) -> bool:
    """Recruiters post on behalf of clients, so their postings are not buying signals."""
    normalized = normalize_name(name)
    return any(word in normalized for word in AGENCY_KEYWORDS)


def clean_domain(domain: str) -> str:
    d = domain.strip().lower()
    return d[4:] if d.startswith("www.") else d


def merge_by_domain(postings: list[dict]) -> list[dict]:
    """One account per domain, with every posting as a signal.

    Postings with no domain are dropped (we never guess one), and so are agencies.
    The same (source, posting_id) counts once. Accounts keep first-seen order.
    """
    accounts: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for p in postings:
        domain = clean_domain(p.get("domain") or "")
        if not domain or looks_like_agency(p["company_name"]):
            continue
        key = (p["source"], p["posting_id"])
        if key in seen:
            continue
        seen.add(key)
        account = accounts.setdefault(domain, {
            "domain": domain,
            "company_name": p["company_name"],
            "normalized_name": normalize_name(p["company_name"]),
            "signals": [],
            "sources": [],
        })
        account["signals"].append(p)
        if p["source"] not in account["sources"]:
            account["sources"].append(p["source"])
    for account in accounts.values():
        account["sources"].sort()
    return list(accounts.values())
