from radar import http
from radar.sources import adzuna, arbeitsagentur
from tests.fakes import FakeResponse


def test_adzuna_parse_strips_markup_and_skips_missing_company():
    data = {"results": [
        {"id": 7, "title": "<strong>ISMS</strong> Manager", "company": {"display_name": "Acme GmbH"},
         "location": {"display_name": "Berlin"}, "created": "2026-11-01T08:00:00Z", "redirect_url": "https://x/7"},
        {"id": 8, "title": "No company", "company": {}},
    ]}
    out = adzuna.parse(data, "ISMS")
    assert len(out) == 1
    assert out[0] == {"posting_id": "7", "source": "adzuna", "company_name": "Acme GmbH",
                      "title": "ISMS Manager", "location": "Berlin", "created": "2026-11-01T08:00:00Z",
                      "url": "https://x/7", "query": "ISMS"}


def test_adzuna_search_stops_at_a_short_page(monkeypatch):
    full = {"results": [{"id": i, "title": "t", "company": {"display_name": f"C{i}"}} for i in range(adzuna.PER_PAGE)]}
    short = {"results": [{"id": 999, "title": "t", "company": {"display_name": "Last"}}]}
    pages = iter([FakeResponse(200, full), FakeResponse(200, short), FakeResponse(200, full)])
    calls = []
    monkeypatch.setattr(http, "request", lambda *a, **k: calls.append(a) or next(pages))
    out = adzuna.search("ISMS", country="de", max_pages=5)
    assert len(calls) == 2 and len(out) == adzuna.PER_PAGE + 1


def test_adzuna_search_respects_the_page_cap(monkeypatch):
    full = {"results": [{"id": i, "title": "t", "company": {"display_name": "C"}} for i in range(adzuna.PER_PAGE)]}
    calls = []
    monkeypatch.setattr(http, "request", lambda *a, **k: calls.append(a) or FakeResponse(200, full))
    adzuna.search("ISMS", country="de", max_pages=3)
    assert len(calls) == 3


def test_arbeitsagentur_parse():
    data = {"stellenangebote": [
        {"refnr": "10001-X-S", "titel": "ISB (m/w/d)", "arbeitgeber": "Beta AG",
         "arbeitsort": {"ort": "München"}, "aktuelleVeroeffentlichungsdatum": "2026-11-02"},
        {"refnr": "10002-X-S", "titel": "no employer"},
    ]}
    out = arbeitsagentur.parse(data, "TISAX")
    assert len(out) == 1
    assert out[0]["source"] == "arbeitsagentur" and out[0]["location"] == "München"
    assert out[0]["url"].endswith("/jobdetail/10001-X-S")


def test_arbeitsagentur_search_uses_total_to_stop(monkeypatch):
    data = {"maxErgebnisse": 60, "stellenangebote": [{"refnr": "r", "arbeitgeber": "B", "titel": "t"}]}
    calls = []
    monkeypatch.setattr(http, "request", lambda *a, **k: calls.append(k) or FakeResponse(200, data))
    arbeitsagentur.search("TISAX", max_pages=10)
    assert len(calls) == 2  # 60 results at 50 per page = 2 pages
    assert calls[0]["params"]["zeitarbeit"] == "false"
