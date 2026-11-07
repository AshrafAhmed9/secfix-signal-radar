import pytest

from radar import db, domain, enrich, http
from tests.fakes import FakeResponse

GOOD = {"industry": "Software", "employee_band": "50-249", "is_automotive_supplier": False,
        "sells_b2b": True, "already_certified": [], "nis2_sector": "none", "evidence": "x"}


def test_html_to_text_drops_scripts_and_styles():
    html = "<html><style>p{}</style><script>var x=1</script><body><h1>Hello</h1><p>World  here</p></body></html>"
    assert enrich.html_to_text(html) == "Hello World here"


def test_find_competitors():
    assert enrich.find_competitors("<a href='https://trust.vanta.com'>Trust</a> and DRATA") == ["vanta", "drata"]
    assert enrich.find_competitors("nothing here") == []


def test_robots_disallow_blocks_fetching(monkeypatch):
    monkeypatch.setattr(http, "request",
                        lambda *a, **k: FakeResponse(200) if False else _Robots("User-agent: *\nDisallow: /"))
    assert enrich.allowed_by_robots("acme.de") is False


def test_unreadable_robots_means_allowed(monkeypatch):
    def boom(*a, **k):
        raise http.RequestFailed("x", 404)
    monkeypatch.setattr(http, "request", boom)
    assert enrich.allowed_by_robots("acme.de") is True


class _Robots:
    status_code = 200
    text = ""

    def __init__(self, text):
        self.text = text


def test_enrich_calls_claude_once_then_serves_from_cache(tmp_path, monkeypatch):
    conn = db.connect(str(tmp_path / "t.db"))
    asked = []
    monkeypatch.setattr(enrich, "fetch_site", lambda d: ("text", "<html>vanta</html>"))
    monkeypatch.setattr(enrich.llm, "ask_json", lambda *a, **k: (asked.append(1) or dict(GOOD), 0.01))
    first, cost1 = enrich.enrich(conn, None, "acme.de", "Acme")
    second, cost2 = enrich.enrich(conn, None, "acme.de", "Acme")
    assert len(asked) == 1 and cost1 == 0.01 and cost2 == 0.0
    assert first == second and first["uses_competitor"] is True


def test_name_in_page_requires_the_first_word():
    assert domain.name_in_page("brainlab", "Welcome to Brainlab, medtech")
    assert not domain.name_in_page("brainlab", "Domain for sale")
    assert not domain.name_in_page("ab", "ab ab ab")  # too short to be evidence


def test_resolve_accepts_a_verified_domain_and_caches_a_miss(tmp_path, monkeypatch):
    conn = db.connect(str(tmp_path / "t.db"))
    monkeypatch.setattr(domain, "verify", lambda d, n: True)
    monkeypatch.setattr(domain.llm, "ask_json", lambda *a, **k: ({"domain": "https://www.Acme.de/home"}, 0.001))
    found, _ = domain.resolve_domain(conn, None, "Acme GmbH", "Berlin", "m")
    assert found == "acme.de"

    monkeypatch.setattr(domain.llm, "ask_json", lambda *a, **k: ({"domain": None}, 0.001))
    assert domain.resolve_domain(conn, None, "Mystery Co", "", "m")[0] is None
    monkeypatch.setattr(domain.llm, "ask_json", lambda *a, **k: pytest.fail("cached miss must not re-ask"))
    assert domain.resolve_domain(conn, None, "Mystery Co", "", "m") == (None, 0.0)


def test_resolve_rejects_job_boards_and_unverified_guesses(tmp_path, monkeypatch):
    conn = db.connect(str(tmp_path / "t.db"))
    monkeypatch.setattr(domain, "verify", lambda d, n: True)
    monkeypatch.setattr(domain.llm, "ask_json", lambda *a, **k: ({"domain": "linkedin.com"}, 0.0))
    assert domain.resolve_domain(conn, None, "Acme GmbH", "", "m")[0] is None
    monkeypatch.setattr(domain, "verify", lambda d, n: False)
    monkeypatch.setattr(domain.llm, "ask_json", lambda *a, **k: ({"domain": "wrong-site.de"}, 0.0))
    assert domain.resolve_domain(conn, None, "Beta AG", "", "m")[0] is None
