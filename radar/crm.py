"""HubSpot company upsert, via the shared HTTP helper."""
from radar import http
from radar.normalize import clean_domain

API = "https://api.hubapi.com"

# Custom company properties the pipeline writes. Created on first run if missing.
CUSTOM_PROPERTIES = [
    {"name": "signal_score", "label": "Signal score", "type": "number", "fieldType": "number"},
    {"name": "signal_reasons", "label": "Signal reasons", "type": "string", "fieldType": "textarea"},
    {"name": "last_signal_date", "label": "Last signal date", "type": "date", "fieldType": "date"},
    {"name": "account_brief", "label": "Account brief", "type": "string", "fieldType": "textarea"},
    {"name": "secfix_segment", "label": "Secfix segment", "type": "string", "fieldType": "text"},
]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
    if brief is not None:  # never overwrite an existing brief with nothing
        props["account_brief"] = brief
    return props


def upsert_company(account: dict, result: dict, *, token: str, owner_id: str | None = None,
                   segment: str | None = None, brief: str | None = None,
                   today: str | None = None) -> tuple[str, str]:
    """Create or update the HubSpot company for this account, never a duplicate.

    Search by domain first. If the search fails we raise and create nothing: creating
    after a failed search is exactly how duplicates happen.
    Returns (hubspot_id, "created" | "updated").
    """
    headers = _headers(token)
    domain = clean_domain(account["domain"])
    search = http.request("POST", f"{API}/crm/v3/objects/companies/search", headers=headers, json={
        "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": domain}]}],
        "limit": 1,
    })
    matches = search.json().get("results", [])
    body = {"properties": build_properties(account, result, owner_id=owner_id, segment=segment,
                                           brief=brief, today=today)}
    if matches:
        company_id = matches[0]["id"]
        http.request("PATCH", f"{API}/crm/v3/objects/companies/{company_id}", headers=headers, json=body)
        return company_id, "updated"
    created = http.request("POST", f"{API}/crm/v3/objects/companies", headers=headers, json=body)
    return created.json()["id"], "created"


def ensure_properties(token: str) -> list[str]:
    """Create any missing custom company properties. Returns the names it created."""
    headers = _headers(token)
    existing = http.request("GET", f"{API}/crm/v3/properties/companies", headers=headers).json()
    have = {p["name"] for p in existing.get("results", [])}
    created = []
    for prop in CUSTOM_PROPERTIES:
        if prop["name"] in have:
            continue
        http.request("POST", f"{API}/crm/v3/properties/companies", headers=headers,
                     json={**prop, "groupName": "companyinformation"})
        created.append(prop["name"])
    return created


def company_url(portal_id: str, company_id: str) -> str:
    return f"https://app.hubspot.com/contacts/{portal_id}/record/0-2/{company_id}"
