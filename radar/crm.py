"""HubSpot company upsert.

Ashraf implements upsert_company(). build_properties() is done.
Tests in tests/test_crm.py define the behaviour.
"""
from radar import http

API = "https://api.hubapi.com"


def clean_domain(domain: str) -> str:
    d = domain.strip().lower()
    return d[4:] if d.startswith("www.") else d


def build_properties(account: dict, result: dict, *, owner_id: str | None = None,
                     segment: str | None = None, brief: str | None = None,
                     today: str | None = None) -> dict:
    """HubSpot property dict for one account. HubSpot wants string values."""
    props = {
        "name": account["company_name"],
        "domain": clean_domain(account["domain"]),
        "signal_score": str(result["score"]),
        "signal_reasons": "\n".join(result["reasons"]),
    }
    if today:
        props["last_signal_date"] = today  # YYYY-MM-DD
    if owner_id:
        props["hubspot_owner_id"] = owner_id
    if segment:
        props["secfix_segment"] = segment
    if brief is not None:  # never overwrite an existing brief with an empty one
        props["account_brief"] = brief
    return props


def upsert_company(account: dict, result: dict, *, token: str, owner_id: str | None = None,
                   segment: str | None = None, brief: str | None = None,
                   today: str | None = None) -> tuple[str, str]:
    """Create or update the HubSpot company for this account. Never creates a duplicate.

    Returns (hubspot_id, "created" | "updated").
    Steps, all through http.request(method, url, headers=..., json=...) with method and
    url as the first two positional arguments:
    1. Search first: POST {API}/crm/v3/objects/companies/search with a filter
       domain EQ clean_domain(account["domain"]). Response: {"results": [{"id": "..."}]}.
    2. Match found (use the first result): PATCH {API}/crm/v3/objects/companies/{id}
       with {"properties": build_properties(...)} -> "updated".
    3. No match: POST {API}/crm/v3/objects/companies with the same body -> "created";
       the new id is in the response JSON "id".
    Auth header: Authorization: Bearer <token>. If the search call fails (RequestFailed),
    let it propagate and do NOT create anything.
    """
    raise NotImplementedError  # Ashraf implements
