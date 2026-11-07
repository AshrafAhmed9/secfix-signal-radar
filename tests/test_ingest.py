import pytest

from radar import http, ingest


def posting(pid, title="ISMS Manager", source="fake"):
    return {"posting_id": pid, "source": source, "company_name": "Acme", "title": title,
            "location": "", "created": "", "url": "u", "query": "q"}


@pytest.mark.parametrize("title,expected", [
    ("Informationssicherheitsbeauftragter (m/w/d)", True),
    ("Information Security Officer", True),
    ("ISMS Manager", True),
    ("TISAX Auditor", True),
    ("Senior Java Developer", False),
    ("Vertriebsleiter", False),
])
def test_is_security_role(title, expected):
    assert ingest.is_security_role(title) is expected


def test_fetch_dedupes_filters_titles_and_survives_a_failing_call(monkeypatch):
    def search(query, *, country, max_pages):
        if query == "bad":
            raise http.RequestFailed("boom", 500)
        return [posting("1"), posting("1"), posting("2", title="Java Developer")]

    monkeypatch.setitem(ingest.SOURCES, "fake", (search, [None]))
    postings, stats = ingest.fetch_postings(["fake"], ["good", "bad"], max_pages=1)
    assert [p["posting_id"] for p in postings] == ["1"]
    assert stats["failed"] == 1
    assert stats["irrelevant"] == 1
    assert stats["raw"]["fake"] == 3
