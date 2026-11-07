"""Adzuna Jobs API (free key). Returns postings in the common shape."""
import re

from radar import config, http

BASE = "https://api.adzuna.com/v1/api/jobs"
PER_PAGE = 50


def parse(data: dict, query: str) -> list[dict]:
    postings = []
    for r in data.get("results", []):
        company = (r.get("company") or {}).get("display_name")
        if not company:
            continue
        postings.append({
            "posting_id": str(r["id"]),
            "source": "adzuna",
            "company_name": company,
            "title": re.sub(r"<[^>]+>", "", r.get("title", "")),  # Adzuna wraps matches in <strong>
            "location": (r.get("location") or {}).get("display_name", ""),
            "created": r.get("created", ""),
            "url": r.get("redirect_url", ""),
            "query": query,
        })
    return postings


def search(query: str, *, country: str, max_pages: int) -> list[dict]:
    postings: list[dict] = []
    for page in range(1, max_pages + 1):
        response = http.request("GET", f"{BASE}/{country}/search/{page}", params={
            "app_id": config.ADZUNA_APP_ID,
            "app_key": config.ADZUNA_APP_KEY,
            "what_phrase": query,
            "results_per_page": PER_PAGE,
            "max_days_old": 30,
            "sort_by": "date",
            "content-type": "application/json",
        })
        data = response.json()
        postings += parse(data, query)
        if len(data.get("results", [])) < PER_PAGE:
            break  # last page
    return postings
