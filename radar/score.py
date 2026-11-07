"""Rule-based, explainable account scoring. No ML: a rep can see exactly why a score is what it is."""
from radar import config


def score_account(account: dict, enrichment: dict | None) -> dict:
    """Score one account 0-100. Returns {"score": int, "reasons": [str]}.

    Every point has a reason that starts with its signed points ("+30 ...").
    Reasons are sorted by absolute points, biggest first, so the digest can show the top two.
    Without enrichment only the posting rules apply, and a reason says so.
    """
    weights = config.WEIGHTS
    items: list[tuple[int, str]] = []

    def add(rule: str, text: str) -> None:
        items.append((weights[rule], text))

    signals = account["signals"]
    add("hiring_infosec_role", f"hiring for a security role ({signals[0]['url']})")
    if len(signals) >= 2:
        add("two_or_more_postings", f"{len(signals)} such postings ({signals[1]['url']})")
    if len(account["sources"]) >= 2:
        add("found_on_both_sources", "posted on both job sources")

    if enrichment is None:
        items.append((0, "not enriched, scored on postings only"))
    else:
        band = enrichment["employee_band"]
        if enrichment["is_automotive_supplier"]:
            add("automotive_supplier", "automotive supplier (TISAX need)")
        if enrichment["nis2_sector"] != "none" and band in config.BANDS_50_PLUS:
            add("nis2_sector_50_plus", f"likely NIS2-regulated ({enrichment['nis2_sector']})")
        if enrichment["sells_b2b"]:
            add("sells_b2b", "sells B2B")
        if band in config.BANDS_IN_ICP:
            add("size_20_to_999", f"{band} employees")
        if enrichment["already_certified"]:
            add("already_certified", "already certified: " + ", ".join(enrichment["already_certified"]))
        if enrichment["uses_competitor"]:
            add("uses_competitor", "site mentions a compliance-software competitor")

    total = max(0, min(100, sum(points for points, _ in items)))
    items.sort(key=lambda item: -abs(item[0]))  # stable: ties keep rule order
    return {"score": total, "reasons": [f"{points:+d} {text}" for points, text in items]}
