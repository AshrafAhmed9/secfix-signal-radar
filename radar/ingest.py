"""Stage 1: pull hiring signals from every enabled source."""
from radar import config, http
from radar.log import log
from radar.sources import adzuna, arbeitsagentur

# country=None means "the source has no country parameter" (the BA API is Germany only).
SOURCES = {
    "adzuna": (adzuna.search, config.COUNTRIES),
    "arbeitsagentur": (arbeitsagentur.search, [None]),
}


def is_security_role(title: str) -> bool:
    """The search also matches job descriptions, so check the title really is a security role."""
    lowered = title.lower()
    return any(word in lowered for word in config.SECURITY_TITLE_WORDS)


def fetch_postings(source_names: list[str], queries: list[str], max_pages: int) -> tuple[list[dict], dict]:
    """Fetch from every source and query. A failing source or query is logged and skipped.

    Returns (postings, stats). stats has per-source counts and "failed" (number of failed calls).
    """
    seen: set[tuple[str, str]] = set()
    postings: list[dict] = []
    stats: dict = {"failed": 0, "raw": {}, "irrelevant": 0}
    for name in source_names:
        search, countries = SOURCES[name]
        stats["raw"][name] = 0
        for country in countries:
            for query in queries:
                try:
                    found = search(query, country=country, max_pages=max_pages)
                except http.RequestFailed as exc:
                    stats["failed"] += 1
                    log("ingest", "source call failed", source=name, query=query, country=country,
                        status=exc.status, error=str(exc))
                    continue
                stats["raw"][name] += len(found)
                for posting in found:
                    key = (posting["source"], posting["posting_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    if not is_security_role(posting["title"]):
                        stats["irrelevant"] += 1
                        continue
                    postings.append(posting)
    return postings, stats
