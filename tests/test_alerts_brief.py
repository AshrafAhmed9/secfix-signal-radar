from radar import alerts, brief


def acct(name, score, segment, hid="9"):
    return {"company_name": name, "domain": f"{name.lower()}.de", "score": score,
            "reasons": ["+30 hiring (https://x/1)", "+25 automotive", "+15 sells B2B"],
            "segment": segment, "hubspot_id": hid}


def test_digest_groups_by_segment_and_shows_two_reasons_and_link():
    text = alerts.build_digest([acct("Beta", 90, "Mid-Market"), acct("Acme", 80, "SMB")], portal_id="123")
    assert text.index("Mid-Market") < text.index("SMB")
    assert "+15 sells B2B" not in text  # only the 2 strongest
    assert "+25 automotive" in text
    assert "https://app.hubspot.com/contacts/123/record/0-2/9" in text


def test_digest_escapes_slack_markup_and_handles_no_accounts():
    text = alerts.build_digest([acct("A&B <x>", 50, None, hid=None)])
    assert "&amp;" in text and "&lt;x&gt;" in text and "HubSpot" not in text
    assert alerts.build_digest([]) == "No new accounts to call today."


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


def test_brief_has_five_bullets_and_evidence_comes_from_our_data(monkeypatch):
    data = {"why_now": "Hiring an ISB.", "likely_pain": "Customer questionnaires.",
            "frameworks": ["ISO 27001"], "roles_to_approach": ["CISO"]}
    monkeypatch.setattr(brief.llm, "ask_json", lambda *a, **k: (data, 0.02))
    account = {"company_name": "Acme", "domain": "acme.de",
               "signals": [{"title": "ISB", "location": "Berlin", "created": "2026-11-01T00:00:00Z", "url": "https://real/1"}]}
    text, cost = brief.make_brief(None, account, None, {"score": 40, "reasons": ["+30 hiring"]})
    assert text.count("\n- ") + 1 == 5
    assert "https://real/1" in text and "Framework: ISO 27001" in text and cost == 0.02
