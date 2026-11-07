"""Company-name normalisation and merging postings into accounts.

Ashraf implements this file. Tests in tests/test_normalize.py define the behaviour.
"""

# Token sequences stripped from the END of a name, longest first. Order matters:
# "co kg" has to be tried before "kg", or "foo co kg" would end up as "foo co".
LEGAL_SUFFIXES = [
    ["co", "kg"],
    ["ug", "haftungsbeschränkt"],
    ["gmbh"], ["ag"], ["se"], ["kg"], ["ug"], ["mbh"], ["inc"], ["ltd"],
]

AGENCY_KEYWORDS = ["personal", "recruiting", "consulting", "zeitarbeit", "staffing"]


def normalize_name(name: str) -> str:
    """Lowercase, turn punctuation into spaces, collapse whitespace, strip legal suffixes.

    "Müller GmbH & Co. KG" -> "müller"; "Acme, Inc." -> "acme"; umlauts are kept.
    Strip suffixes repeatedly ("Foo AG & Co. KG" -> "foo"). If stripping would leave
    nothing (a company literally called "SE"), keep the lowercased name instead.
    """
    raise NotImplementedError  # Ashraf implements


def looks_like_agency(name: str) -> bool:
    """True when the normalised name contains an AGENCY_KEYWORDS substring.

    Recruiters post on behalf of clients, so their postings are not buying signals.
    "Hays Personal GmbH" -> True, "Acme Recruiting AG" -> True, "Siemens AG" -> False.
    """
    raise NotImplementedError  # Ashraf implements


def merge_by_domain(postings: list[dict]) -> list[dict]:
    """Group postings into one account per domain.

    Each posting has: posting_id, source, company_name, title, location, created, url,
    query, and domain (may be None/"" when it could not be resolved).

    Returns one dict per domain: {"domain", "company_name", "normalized_name",
    "signals": [posting, ...], "sources": sorted list of distinct sources}.
    - Postings without a domain are dropped (never guess).
    - Agencies (looks_like_agency on company_name) are dropped.
    - The same (source, posting_id) seen twice appears once in signals.
    - company_name is the first posting's name; accounts keep first-seen order.
    - The domain is lowercased and a leading "www." removed before grouping.
    """
    raise NotImplementedError  # Ashraf implements
