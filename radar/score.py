"""Rule-based, explainable account scoring (no ML).

Ashraf implements this file. Weights live in radar.config.WEIGHTS. Tests in
tests/test_score.py define the behaviour.
"""
from radar import config  # noqa: F401  (used once implemented)


def score_account(account: dict, enrichment: dict | None) -> dict:
    """Score one account 0-100 and say why.

    account: output of merge_by_domain ("signals" list of postings, "sources" list).
    enrichment: the Claude result plus "uses_competitor": bool, with keys
        employee_band, is_automotive_supplier, sells_b2b, already_certified (list),
        nis2_sector (str, "none" if not regulated). None when enrichment failed.

    Returns {"score": int, "reasons": [str, ...]}.
    Rules (points from config.WEIGHTS):
    - hiring_infosec_role: any signal (every account has one)
    - two_or_more_postings: 2+ signals
    - found_on_both_sources: 2+ distinct sources
    - automotive_supplier, sells_b2b: from enrichment
    - nis2_sector_50_plus: nis2_sector != "none" AND band in config.BANDS_50_PLUS
    - size_20_to_999: band in config.BANDS_IN_ICP
    - already_certified: non-empty list (negative)
    - uses_competitor: True (negative)
    Enrichment None: only the signal rules apply, plus a reason saying it was not enriched.
    Clamp to 0..100. Each reason starts with its signed points ("+30 ...", "-50 ...").
    The hiring_infosec_role reason includes signals[0]["url"]; the two_or_more_postings
    reason includes signals[1]["url"] (evidence a rep can click).
    Reasons are ordered by absolute points, biggest first (ties keep rule order).
    """
    raise NotImplementedError  # Ashraf implements
