import json

import pytest

from radar import crm, http
from tests.fakes import FakeResponse

ACCOUNT = {"domain": "acme.de", "company_name": "Acme GmbH"}
RESULT = {"score": 85, "reasons": ["+30 hiring (https://example.test/1)", "+25 automotive"]}


def script(monkeypatch, outcomes):
    calls = []
    outcomes = iter(outcomes)

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(crm.http, "request", fake_request)
    return calls


def upsert(**kw):
    kw.setdefault("token", "tok")
    return crm.upsert_company(kw.pop("account", ACCOUNT), RESULT, **kw)


def test_creates_when_search_finds_nothing(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200, {"results": []}), FakeResponse(201, {"id": "999"})])
    assert upsert() == ("999", "created")
    assert [c["method"] for c in calls] == ["POST", "POST"]
    assert calls[0]["url"].endswith("/crm/v3/objects/companies/search")  # search BEFORE create
    assert calls[1]["url"].endswith("/crm/v3/objects/companies")
    assert calls[1]["json"]["properties"]["domain"] == "acme.de"


def test_updates_the_first_match_and_does_not_create(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200, {"results": [{"id": "123"}, {"id": "456"}]}),
                                 FakeResponse(200, {"id": "123"})])
    assert upsert() == ("123", "updated")
    assert len(calls) == 2
    assert calls[1]["method"] == "PATCH"
    assert calls[1]["url"].endswith("/crm/v3/objects/companies/123")


def test_search_uses_the_cleaned_domain(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200, {"results": []}), FakeResponse(201, {"id": "1"})])
    upsert(account={"domain": "WWW.Acme.DE", "company_name": "Acme GmbH"})
    assert '"acme.de"' in json.dumps(calls[0]["json"])


def test_sends_bearer_token(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200, {"results": []}), FakeResponse(201, {"id": "1"})])
    upsert(token="secret-token")
    assert all(c["headers"]["Authorization"] == "Bearer secret-token" for c in calls)


def test_brief_is_only_sent_when_given(monkeypatch):
    calls = script(monkeypatch, [FakeResponse(200, {"results": [{"id": "1"}]}), FakeResponse(200, {"id": "1"}),
                                 FakeResponse(200, {"results": [{"id": "1"}]}), FakeResponse(200, {"id": "1"})])
    upsert()
    upsert(brief="five bullets")
    assert "account_brief" not in calls[1]["json"]["properties"]
    assert calls[3]["json"]["properties"]["account_brief"] == "five bullets"


def test_failed_search_propagates_and_creates_nothing(monkeypatch):
    calls = script(monkeypatch, [http.RequestFailed("down", 500)])
    with pytest.raises(http.RequestFailed):
        upsert()
    assert len(calls) == 1


def test_build_properties_formats_values_for_hubspot():
    props = crm.build_properties(ACCOUNT, RESULT, owner_id="42", segment="SMB", today="2026-11-09")
    assert props["signal_score"] == "85"
    assert props["signal_reasons"] == "\n".join(RESULT["reasons"])
    assert props["hubspot_owner_id"] == "42" and props["secfix_segment"] == "SMB"
    assert props["last_signal_date"] == "2026-11-09"
    assert "account_brief" not in props


def test_build_properties_keeps_an_explicit_empty_brief_out_of_the_way():
    assert "account_brief" not in crm.build_properties(ACCOUNT, RESULT)
    assert crm.build_properties(ACCOUNT, RESULT, brief="x")["account_brief"] == "x"
