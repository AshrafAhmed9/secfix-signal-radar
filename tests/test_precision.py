from eval import precision

LABELS = [
    {"rank": "1", "domain": "a.de", "name": "A", "score": "100", "fit": "y", "reason": ""},
    {"rank": "2", "domain": "b.de", "name": "B", "score": "90", "fit": "n", "reason": "staffing firm"},
    {"rank": "3", "domain": "c.de", "name": "C", "score": "80", "fit": "", "reason": ""},
    {"rank": "7", "domain": "d.de", "name": "D", "score": "60", "fit": "Y", "reason": ""},
]


def test_precision_counts_only_labelled_rows_in_the_top_k():
    assert precision.precision_at(LABELS, 5) == (0.5, 2)       # rows 1 and 2; row 3 is unlabelled
    p, n = precision.precision_at(LABELS, 10)
    assert n == 3 and round(p, 3) == 0.667                      # row 7 counts, case-insensitive


def test_precision_is_none_when_nothing_is_labelled():
    assert precision.precision_at([{**LABELS[2]}], 10) is None
