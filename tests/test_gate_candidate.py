"""tools/gate_candidate: the R1 bundle as a candidate, and broken copies of it.

The simulation tests need the pinned Verilator (run them in the toolchain image).
Every candidate is built from R1's real files under tmp_path, renamed to P1, and
gated against a copy of the pack; designs/ must stay byte-identical.
"""

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

from closure_core import candidate, gates, policy
from closure_core.design import find_repo_root

ROOT = find_repo_root()
PACK = ROOT / "designs" / "uart"
FATAL = 'if (!saw_frame_error) $fatal(1, "frame_error never pulsed");'
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")


def r1_candidate(d: Path, i: str = "P1") -> Path:
    item = next(x for x in yaml.safe_load((PACK / "plan.yaml").read_text())["items"] if x["id"] == "R1")
    item.update(id=i, cover=f"{i}_frame_error", cover_module=f"cov_{i}")
    d.mkdir(parents=True)
    (d / "item.yaml").write_text(yaml.safe_dump(item, sort_keys=False))
    (d / "cover.sv").write_text((PACK / "covers" / "R1.sv").read_text().replace("R1", i))
    shutil.copy(PACK / "gold" / "R1.sv", d / "gold.sv")
    (d / "near_miss").mkdir()
    shutil.copy(PACK / "near_miss" / "R1_good_stop.sv", d / "near_miss" / "good_stop.sv")
    return d


def empty_pack(d: Path) -> Path:
    """The pack with no plan items, so a renamed R1 is not its own duplicate."""
    shutil.copytree(PACK, d)
    plan = yaml.safe_load((d / "plan.yaml").read_text())
    (d / "plan.yaml").write_text(yaml.safe_dump({**plan, "items": []}, sort_keys=False))
    (d / "multi.yaml").write_text("multi: []\n")  # an empty plan has no multi-target tasks
    for f in [*(d / "covers").glob("*.sv"), *(d / "gold").glob("*.sv"), *(d / "near_miss").glob("*.sv")]:
        f.unlink()
    return d


def tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + p.read_bytes())
    return h.hexdigest()


def run(tmp_path: Path, cand: Path, base: Path | None = None, **kw) -> dict:
    cache = tmp_path / "mutation_cache.json"
    shared = gates.MUTATION_CACHE
    if shared.exists() and not cache.exists():
        shutil.copy(shared, cache)  # reuse cached baseline runs; never write the shared cache
    before = tree_hash(ROOT / "designs")
    res = candidate.gate(base or empty_pack(tmp_path / "base"), cand, cache_path=cache, j=2, **kw)
    assert tree_hash(ROOT / "designs") == before, "gating wrote into designs/"
    return res


def gate_of(res: dict, name: str) -> dict:
    return next(g for g in res["gates"] if g["gate"] == name)


# --- format: pure, no simulator ---------------------------------------------------------

def test_format_rejects_missing_cover(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    (cand / "cover.sv").unlink()
    res = candidate.gate(PACK, cand, cache_path=tmp_path / "cache.json")
    assert res["failed_gate"] == "format" and "cover.sv" in gate_of(res, "format")["detail"]


def test_format_allows_missing_gold(tmp_path):
    """Without gold.sv the formal gate finds one (tests/test_formal_gate.py)."""
    cand = r1_candidate(tmp_path / "c")
    (cand / "gold.sv").unlink()
    assert candidate.check_format(cand, set()).ok is True


def test_format_rejects_existing_id(tmp_path):
    res = candidate.gate(PACK, r1_candidate(tmp_path / "c", "R1"), cache_path=tmp_path / "cache.json")
    assert res["failed_gate"] == "format" and "already in the plan" in gate_of(res, "format")["detail"]


# --- full gate runs ---------------------------------------------------------------------

@needs_sim
def test_r1_bundle_is_accepted(tmp_path):
    res = run(tmp_path, r1_candidate(tmp_path / "c"))
    assert res["accepted"], res
    assert [g["gate"] for g in res["gates"]] == candidate.ORDER and not res["skipped"]
    assert gate_of(res, "value")["data"]["evidence"] == "both"
    # A candidate with its own gold: formal does not run, the gold keeps today's rules.
    assert gate_of(res, "formal")["ok"] == "n/a" and gate_of(res, "formal")["data"]["gold_source"] == "llm"
    assert gate_of(res, "gold")["data"]["gold_source"] == "llm"


@needs_sim
def test_bad_citation_fails_at_citations(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    item = yaml.safe_load((cand / "item.yaml").read_text())
    item["sources"][1]["anchor"] = "this sentence is not in the README"
    (cand / "item.yaml").write_text(yaml.safe_dump(item, sort_keys=False))
    res = run(tmp_path, cand)
    assert res["failed_gate"] == "citations", res
    assert res["skipped"] == candidate.ORDER[candidate.ORDER.index("citations") + 1:]


@needs_sim
def test_gold_that_misses_fails_at_gold(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    g = (cand / "gold.sv").read_text()
    (cand / "gold.sv").write_text(g.replace("send_frame(8'h55, 1'b0);", "send_frame(8'h55, 1'b1);"))
    res = run(tmp_path, cand)
    assert res["failed_gate"] == "gold", res
    assert "runtime_error" in gate_of(res, "gold")["detail"]  # its own $fatal fires


@needs_sim
def test_inert_assert_gold_fails_at_gold(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    g = (cand / "gold.sv").read_text()
    assert FATAL in g
    (cand / "gold.sv").write_text(g.replace(FATAL, "assert (saw_frame_error);"))
    res = run(tmp_path, cand)
    assert res["failed_gate"] == "gold", res
    assert "assert/assume never fires" in gate_of(res, "gold")["detail"]


@needs_sim
def test_policy_violating_cover_fails_at_cover_policy(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    c = (cand / "cover.sv").read_text()
    (cand / "cover.sv").write_text(c.replace("endmodule", "  initial $finish;\nendmodule"))
    res = run(tmp_path, cand)
    assert res["failed_gate"] == "cover_policy", res


@needs_sim
def test_copy_of_r1_fails_at_duplicate(tmp_path):
    res = run(tmp_path, r1_candidate(tmp_path / "c"), base=PACK)
    assert res["failed_gate"] == "duplicate", res
    assert "R1" in gate_of(res, "duplicate")["detail"]


@needs_sim
def test_near_miss_overlap_is_reported(tmp_path):
    cand = r1_candidate(tmp_path / "c")  # has good_stop: same path except the stop bit
    # Does nothing: passes the near-miss gate vacuously.
    (cand / "near_miss" / "idle.sv").write_text("module tb; initial $finish; endmodule\n")
    res = run(tmp_path, cand)
    nm = gate_of(res, "near_miss")
    assert nm["ok"] is True, res
    overlap = nm["data"]["overlap"]
    assert nm["data"]["low_overlap"] == ["P1_idle.sv"]
    assert overlap["P1_good_stop.sv"] > overlap["P1_idle.sv"]


@needs_sim
def test_near_miss_required_unless_waived(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    shutil.rmtree(cand / "near_miss")
    res = run(tmp_path, cand)
    assert res["failed_gate"] == "near_miss" and "no near-miss" in gate_of(res, "near_miss")["detail"]

    item = yaml.safe_load((cand / "item.yaml").read_text())
    item["near_miss_waiver"] = "test: no meaningful near-miss"
    (cand / "item.yaml").write_text(yaml.safe_dump(item, sort_keys=False))
    (tmp_path / "w").mkdir()
    res = run(tmp_path / "w", cand)
    nm = gate_of(res, "near_miss")
    assert nm["ok"] is True and nm["data"]["opted_out"] == "test: no meaningful near-miss"


def test_near_miss_waiver_with_near_misses_fails():
    from closure_core.design import PlanItem
    from closure_core.gates import near_miss
    from closure_core.grader import GradeResult
    it = PlanItem("P1", "P1_x", "cov_P1", "d", "T0", near_miss_waiver="why")
    r = GradeResult("uart", ["P1"], "ok", 0.0, {"P1": 0}, {"P1": 0}, 0, 0, "")
    assert near_miss(it, [("a.sv", r)]).ok is False
