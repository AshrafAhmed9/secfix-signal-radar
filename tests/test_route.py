from radar import route

OWNERS = {"SMB": ["a", "b"], "Mid-Market": ["m"]}


def test_segment_by_band():
    assert route.segment_for("20-49") == "SMB"
    assert route.segment_for("50-249") == "SMB"
    assert route.segment_for("250-999") == "Mid-Market"
    assert route.segment_for("1000+") is None
    assert route.segment_for("1-19") is None
    assert route.segment_for(None) is None


def test_round_robin_inside_a_segment():
    counts = {}
    picks = [route.pick_owner("SMB", counts, OWNERS, "dflt") for _ in range(3)]
    assert picks == ["a", "b", "a"]
    assert route.pick_owner("Mid-Market", counts, OWNERS, "dflt") == "m"


def test_no_segment_or_empty_pool_falls_back_to_default():
    assert route.pick_owner(None, {}, OWNERS, "dflt") == "dflt"
    assert route.pick_owner("SMB", {}, {"SMB": []}, "dflt") == "dflt"
    assert route.pick_owner("SMB", {}, {"SMB": []}, "") is None
