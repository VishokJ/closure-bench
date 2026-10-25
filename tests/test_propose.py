"""Proposer: parsing, ID substitution, summary; and a scripted end-to-end run plus replay.

The end-to-end test needs the pinned Verilator (toolchain image). It scripts the
model: Stage A lists two tasks and a waiver; c01's first bundle has a cover that
violates the policy and is repaired; c02 is the same item again, so it passes
on its own and is rejected at the set stage as a duplicate of c01.
"""

import json
import shutil
import uuid

import pytest
import yaml

from closure_core import policy, propose
from closure_core.design import find_repo_root

ROOT = find_repo_root()
PACK = ROOT / "designs" / "uart"
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")


def r1_bundle(cover_extra: str = "") -> str:
    item = next(x for x in yaml.safe_load((PACK / "plan.yaml").read_text())["items"] if x["id"] == "R1")
    plan = {k: item[k] for k in ("description", "tier", "sources")} | {"cover": "ITEM_frame_error"}
    cover = (PACK / "covers" / "R1.sv").read_text().replace("R1", "ITEM")
    cover = cover.replace("endmodule", cover_extra + "endmodule")
    return (f"<plan>\n{yaml.safe_dump(plan, sort_keys=False)}</plan>\n<cover>\n{cover}</cover>\n"
            f"<gold>\n{(PACK / 'gold' / 'R1.sv').read_text()}</gold>\n"
            f'<near_miss name="good_stop">\n{(PACK / "near_miss" / "R1_good_stop.sv").read_text()}</near_miss>\n')


STAGE_A = """Here they are.
<candidates>
- title: frame error
  kind: task
  target_module: uart_rx
  behaviour: frame_error pulses on a low stop bit
  why_baseline_misses: every baseline frame has a good stop bit
  sources: [{type: DOC, doc: pc16550d, page: 16}]
- title: frame error again
  kind: task
  target_module: uart_rx
  behaviour: the same behaviour, worded differently
  why_baseline_misses: same
  sources: [{type: DOC, doc: pc16550d, page: 17}]
- title: implicit else at uart_rx.v:120
  kind: waiver
  behaviour: unreachable
  why_baseline_misses: bit_cnt can only be 1 there
</candidates>
"""


# --- pure ----------------------------------------------------------------------------------

def test_parse_bundle():
    b = propose.parse_bundle(r1_bundle() + '<near_miss name="late">\nmodule tb; endmodule\n</near_miss>')
    assert b["plan"]["cover"] == "ITEM_frame_error"
    assert "module cov_ITEM" in b["cover"] and "module tb" in b["gold"]
    assert list(b["near_miss"]) == ["good_stop", "late"]


@pytest.mark.parametrize("text, msg", [
    ("<plan>\na: 1\n</plan><cover>x</cover>", "<gold>"),
    ("<plan>\n- 1\n</plan><cover>x</cover><gold>y</gold>", "mapping"),
    ('<plan>\na: 1\n</plan><cover>x</cover><gold>y</gold><near_miss name="Bad">z</near_miss>', "near_miss name"),
])
def test_parse_bundle_errors(text, msg):
    with pytest.raises(propose.ParseError, match=msg):
        propose.parse_bundle(text)


def test_parse_candidates():
    cands = propose.parse_candidates(STAGE_A)
    assert [c["kind"] for c in cands] == ["task", "task", "waiver"]
    with pytest.raises(propose.ParseError):
        propose.parse_candidates("no block")


def test_substitute_only_the_token():
    text = "module cov_ITEM; u_cov_ITEM; ITEM_frame_error; ITEMS; XITEM; P1; P10"
    assert propose.substitute(text, "ITEM", "P1") == \
        "module cov_P1; u_cov_P1; P1_frame_error; ITEMS; XITEM; P1; P10"
    assert propose.substitute("P1 P10 cov_P1", "P1", "R2") == "R2 P10 cov_R2"


def test_write_candidate(tmp_path):
    propose.write_candidate(propose.parse_bundle(r1_bundle()), "P3", tmp_path / "c")
    item = yaml.safe_load((tmp_path / "c" / "item.yaml").read_text())
    assert (item["id"], item["cover"], item["cover_module"]) == ("P3", "P3_frame_error", "cov_P3")
    assert "bind uart_rx cov_P3 u_cov_P3" in (tmp_path / "c" / "cover.sv").read_text()


def test_repair_message_names_gate_and_detail():
    res = {"failed_gate": "cover_policy",
           "gates": [{"gate": "cover_policy", "ok": False, "detail": "x.sv:3: initial is not allowed"}]}
    msg = propose.repair_message(res)
    assert "`cover_policy`" in msg and "initial is not allowed" in msg


def _res(kills=(), holes=(), reqs=()):
    return {"gates": [{"gate": "gold", "data": {"holes_hit": list(holes)}},
                      {"gate": "value", "data": {"kills": list(kills), "requirement_keys": list(reqs)}}]}


def test_progress_counts_only_what_the_run_adds():
    before = {"survivors": ["m1", "m2", "m3"], "killed_by_plan": ["m1"],
              "holes": ["h1", "h2", "h3", "w1"], "waived_holes": ["w1"], "closed_by_plan": ["h1"],
              "requirements_by_plan": ["r1"]}
    p = propose.progress(before, [_res(kills=["m1", "m2"], holes=["h1", "h2", "w1"], reqs=["r1", "r2"]),
                                  _res(kills=["m2", "base_killed"])])
    assert p["mutants"] == {"baseline_survivors": 3, "killed_by_plan": 1, "killed_by_run": ["m2"], "remaining": 1}
    assert p["holes"] == {"baseline": 4, "waived": 1, "closed_by_plan": 1, "closed_by_run": ["h2"],
                          "remaining": ["h3"]}
    assert p["requirements"] == {"cited_by_plan": 1, "new_in_run": ["r2"]}


# --- end to end ----------------------------------------------------------------------------

@pytest.fixture
def scratch():
    d = ROOT / "results" / "tmp" / f"test_propose_{uuid.uuid4().hex[:8]}"  # inside the repo: tools need it
    yield d
    shutil.rmtree(d, ignore_errors=True)


def empty_pack(d):
    shutil.copytree(PACK, d)
    plan = yaml.safe_load((d / "plan.yaml").read_text())
    (d / "plan.yaml").write_text(yaml.safe_dump({**plan, "items": []}, sort_keys=False))
    for f in [*(d / "covers").glob("*.sv"), *(d / "gold").glob("*.sv"), *(d / "near_miss").glob("*.sv")]:
        f.unlink()
    return d


@needs_sim
def test_scripted_run_and_replay(scratch):
    model = propose.ScriptedModel([STAGE_A, r1_bundle("  initial $finish;\n"), r1_bundle(), r1_bundle()])
    ex = propose.Executor(image=None, j=8)
    run_dir = scratch / "run"
    s = propose.run(run_dir, model, ex, base=empty_pack(scratch / "base"))

    assert s["proposed"] == {"tasks": 2, "waivers": 1}
    assert [w["cid"] for w in s["waiver_proposals"]] == ["c03"]
    assert json.loads((run_dir / "gates/c01/0.json").read_text())["failed_gate"] == "cover_policy"
    assert s["repair"] == {"failed_first_attempt": 1, "repaired": 1, "rate": 1.0}
    assert s["rejected_at"] == {} and s["rejected_at_set"] == {"c02": "duplicate"}
    assert s["accepted"] == ["c01"]
    assert s["cites_outside_context_pages"] == ["c02"]       # pc16550d p17 is not a context page
    first = {f["gate"]: f["passed"] for f in s["funnel_first_attempt"]}
    assert (first["proposed"], first["cover_sync"], first["cover_policy"], first["duplicate"]) == (2, 2, 1, 1)
    nm = next(f for f in s["funnel_final"] if f["gate"] == "near_miss")
    assert (nm["passed"], nm["opted_out"]) == (2, 0)
    assert s["hit_by_random"] == {"c01": {"rx": 101}}      # frame errors happen by accident
    prog = s["progress"]                                    # base pack is empty: R1's effect is the run's
    assert prog["mutants"]["killed_by_plan"] == 0 and prog["mutants"]["killed_by_run"]
    assert "v_branch uart_rx.v:122 else" in prog["holes"]["closed_by_run"]
    assert prog["holes"]["waived"] == 48 and prog["requirements"]["cited_by_plan"] == 0
    assert len(prog["requirements"]["new_in_run"]) == 2
    repair = json.loads((run_dir / "responses/c01/1.json").read_text())["messages"][-1]["content"]
    assert "cover_policy" in repair and "initial is not allowed" in repair

    assert propose.replay(run_dir, ex) == []

    # Replay must notice a recorded decision it cannot reproduce.
    g = run_dir / "gates/c02/0.json"
    rec = json.loads(g.read_text())
    rec["accepted"] = False
    g.write_text(json.dumps(rec))
    assert "c02 attempt 0: gate result differs" in propose.replay(run_dir, ex)
