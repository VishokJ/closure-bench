from closure_core import gates


def run(corpus, kills=None):
    out, summary = gates.duplicate(corpus, ["A", "B"], kills or {})
    return {i: (r.ok, r.detail) for i, r in out.items()}, summary


def test_identical_signatures_fail():
    out, _ = run({"gold:A": {"A": 1, "B": 1}, "gold:B": {"A": 1, "B": 1}})
    assert out["A"][0] is False and "B" in out["A"][1]
    assert out["B"][0] is False


def test_overlap_with_witness_passes_and_reports_implication():
    # B's gold also hits A; A's gold hits A but not B, which separates them.
    out, summary = run({"gold:A": {"A": 1, "B": 0}, "gold:B": {"A": 1, "B": 2}})
    assert out["A"][0] is True and out["B"][0] is True
    assert summary["implies"] == {"B": ["A"]}


def test_missing_gold_is_unverified():
    out, _ = run({"gold:A": {"A": 1, "B": 0}})
    assert out["B"][0] is None


def test_same_mutant_kills_reported_not_enforced():
    out, summary = run({"gold:A": {"A": 1, "B": 0}, "gold:B": {"A": 0, "B": 1}},
                       kills={"A": ["m1"], "B": ["m1"]})
    assert out["A"][0] is True and "same mutant kills as B" in out["A"][1]
    assert summary["same_mutant_kills"] == {"A": ["B"], "B": ["A"]}


def test_empty_kills_are_not_the_same():
    _, summary = run({"gold:A": {"A": 1, "B": 0}, "gold:B": {"A": 0, "B": 1}},
                     kills={"A": [], "B": []})
    assert summary["same_mutant_kills"] == {}
