"""Bundesagentur für Arbeit Jobsuche API (free, public key). Germany only.

Field names follow the community docs (github.com/bundesAPI/jobsuche-api). Not yet verified
against a live response from this project: the first real run will show.
"""
from radar import http

URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
PER_PAGE = 50
HEADERS = {"X-API-Key": "jobboerse-jobsuche"}  # public client id published in the API docs


def parse(data: dict, query: str) -> list[dict]:
    postings = []
    for r in data.get("stellenangebote", []):
        if not r.get("arbeitgeber") or not r.get("refnr"):
            continue
        postings.append({
            "posting_id": r["refnr"],
            "source": "arbeitsagentur",
            "company_name": r["arbeitgeber"],
            "title": r.get("titel", ""),
            "location": (r.get("arbeitsort") or {}).get("ort", ""),
            "created": r.get("aktuelleVeroeffentlichungsdatum", ""),
            "url": f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{r['refnr']}",
            "query": query,
        })
    return postings


def search(query: str, *, country: str | None = None, max_pages: int) -> list[dict]:
    postings: list[dict] = []
    for page in range(1, max_pages + 1):
        response = http.request("GET", URL, headers=HEADERS, params={
            "was": query,
            "angebotsart": 1,          # regular jobs, not training places
            "zeitarbeit": "false",     # drop staffing agencies at the source
            "veroeffentlichtseit": 30,
            "size": PER_PAGE,
            "page": page,
        })
        data = response.json()
        postings += parse(data, query)
        if page * PER_PAGE >= int(data.get("maxErgebnisse", 0) or 0):
            break
    return postings
