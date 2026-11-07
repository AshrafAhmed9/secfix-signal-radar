import pytest

from radar.config import WEIGHTS as W
from radar.score import score_account


def account(n_signals=1, sources=("adzuna",)):
    signals = [{"posting_id": str(i), "source": sources[0], "url": f"https://example.test/{i}"}
               for i in range(n_signals)]
    return {"domain": "acme.de", "company_name": "Acme", "signals": signals, "sources": list(sources)}


def enrichment(**kw):
    base = {"employee_band": "1-19", "is_automotive_supplier": False, "sells_b2b": False,
            "already_certified": [], "nis2_sector": "none", "uses_competitor": False}
    base.update(kw)
    return base


def test_single_posting_scores_only_the_hiring_rule():
    out = score_account(account(), enrichment())
    assert out["score"] == W["hiring_infosec_role"]
    assert isinstance(out["score"], int)
    assert len(out["reasons"]) == 1
    assert out["reasons"][0].startswith(f"+{W['hiring_infosec_role']} ")


def test_two_postings_and_two_sources_add_points():
    out = score_account(account(2, ("adzuna", "arbeitsagentur")), enrichment())
    assert out["score"] == (W["hiring_infosec_role"] + W["two_or_more_postings"]
                            + W["found_on_both_sources"])


def test_automotive_and_b2b_add_points():
    out = score_account(account(), enrichment(is_automotive_supplier=True, sells_b2b=True))
    assert out["score"] == W["hiring_infosec_role"] + W["automotive_supplier"] + W["sells_b2b"]


@pytest.mark.parametrize("band,size_pts", [
    ("1-19", 0), ("20-49", W["size_20_to_999"]), ("50-249", W["size_20_to_999"]),
    ("250-999", W["size_20_to_999"]), ("1000+", 0), ("unknown", 0),
])
def test_size_rule_by_band(band, size_pts):
    out = score_account(account(), enrichment(employee_band=band))
    assert out["score"] == W["hiring_infosec_role"] + size_pts


@pytest.mark.parametrize("band,nis2_applies", [
    ("20-49", False), ("50-249", True), ("250-999", True), ("1000+", True), ("unknown", False),
])
def test_nis2_needs_a_regulated_sector_and_50_plus_employees(band, nis2_applies):
    out = score_account(account(), enrichment(employee_band=band, nis2_sector="Energy"))
    size_pts = W["size_20_to_999"] if band in ("20-49", "50-249", "250-999") else 0
    expected = W["hiring_infosec_role"] + size_pts + (W["nis2_sector_50_plus"] if nis2_applies else 0)
    assert out["score"] == expected


def test_nis2_none_sector_never_applies():
    out = score_account(account(), enrichment(employee_band="250-999", nis2_sector="none"))
    assert out["score"] == W["hiring_infosec_role"] + W["size_20_to_999"]


def test_already_certified_subtracts_and_score_never_goes_below_zero():
    out = score_account(account(), enrichment(already_certified=["ISO27001"]))
    assert out["score"] == 0
    assert any(r.startswith(f"{W['already_certified']} ") for r in out["reasons"])  # "-50 ..."


def test_competitor_subtracts_and_is_explained():
    out = score_account(account(), enrichment(sells_b2b=True, uses_competitor=True))
    assert out["score"] == W["hiring_infosec_role"] + W["sells_b2b"] + W["uses_competitor"]
    assert any(r.startswith(f"{W['uses_competitor']} ") for r in out["reasons"])


def test_score_is_clamped_to_100():
    out = score_account(
        account(2, ("adzuna", "arbeitsagentur")),
        enrichment(employee_band="250-999", is_automotive_supplier=True, sells_b2b=True,
                   nis2_sector="Energy"),
    )
    assert out["score"] == 100


def test_failed_enrichment_still_scores_signals_and_says_so():
    out = score_account(account(2), None)
    assert out["score"] == W["hiring_infosec_role"] + W["two_or_more_postings"]
    assert any("not enriched" in r.lower() for r in out["reasons"])


def test_posting_urls_are_evidence_in_the_hiring_reasons():
    out = score_account(account(2), enrichment())
    assert any("https://example.test/0" in r for r in out["reasons"])
    assert any("https://example.test/1" in r for r in out["reasons"])


def test_reasons_are_ordered_by_absolute_points():
    out = score_account(account(), enrichment(sells_b2b=True, already_certified=["TISAX"],
                                              uses_competitor=True))
    pts = [abs(int(r.split()[0])) for r in out["reasons"]]
    assert pts == sorted(pts, reverse=True)
