import pytest

from radar.normalize import looks_like_agency, merge_by_domain, normalize_name


def posting(**kw):
    base = {"posting_id": "1", "source": "adzuna", "company_name": "Acme GmbH",
            "title": "ISMS Manager", "location": "Berlin", "created": "2026-11-01",
            "url": "https://example.test/1", "query": "ISMS", "domain": "acme.de"}
    base.update(kw)
    return base


@pytest.mark.parametrize("raw,expected", [
    ("Müller GmbH & Co. KG", "müller"),
    ("Acme, Inc.", "acme"),
    ("  Siemens   AG ", "siemens"),
    ("Foo AG & Co. KG", "foo"),
    ("Foo mbH & Co. KG", "foo"),
    ("MÜLLER AG", "müller"),
    ("Dr. Oetker", "dr oetker"),
    ("ACME  Technologies SE", "acme technologies"),
    ("Beta Systems UG (haftungsbeschränkt)", "beta systems"),
    ("SE", "se"),  # stripping would leave nothing, so keep it
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize("name,expected", [
    ("Hays Personal GmbH", True),
    ("Acme Recruiting AG", True),
    ("Randstad Zeitarbeit", True),
    ("Siemens AG", False),
    ("Brainlab SE", False),
])
def test_looks_like_agency(name, expected):
    assert looks_like_agency(name) is expected


def test_same_domain_merges_into_one_account_with_all_signals():
    accounts = merge_by_domain([
        posting(posting_id="1", company_name="Acme GmbH"),
        posting(posting_id="2", company_name="ACME GmbH & Co. KG", title="ISO 27001 Lead"),
    ])
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc["domain"] == "acme.de"
    assert acc["company_name"] == "Acme GmbH"
    assert acc["normalized_name"] == "acme"
    assert [s["posting_id"] for s in acc["signals"]] == ["1", "2"]


def test_domain_is_lowercased_and_www_removed_before_grouping():
    accounts = merge_by_domain([posting(domain="WWW.Acme.DE"), posting(posting_id="2", domain="acme.de")])
    assert len(accounts) == 1 and accounts[0]["domain"] == "acme.de"


def test_postings_without_domain_are_dropped():
    assert merge_by_domain([posting(domain=None), posting(posting_id="2", domain="")]) == []


def test_agencies_are_dropped():
    assert merge_by_domain([posting(company_name="Hays Personal GmbH", domain="hays.de")]) == []


def test_same_posting_seen_twice_counts_once():
    accounts = merge_by_domain([posting(), posting()])
    assert len(accounts[0]["signals"]) == 1


def test_same_posting_id_from_different_sources_are_different_signals():
    accounts = merge_by_domain([posting(source="adzuna"), posting(source="arbeitsagentur")])
    assert len(accounts[0]["signals"]) == 2
    assert accounts[0]["sources"] == ["adzuna", "arbeitsagentur"]


def test_accounts_keep_first_seen_order():
    accounts = merge_by_domain([
        posting(posting_id="1", domain="b.de", company_name="B GmbH"),
        posting(posting_id="2", domain="a.de", company_name="A GmbH"),
        posting(posting_id="3", domain="b.de", company_name="B GmbH"),
    ])
    assert [a["domain"] for a in accounts] == ["b.de", "a.de"]
