"""Proposer: parsing, ID substitution, summary; and a scripted end-to-end run plus replay.

The end-to-end test needs the pinned Verilator (toolchain image). It scripts the
model: Stage A lists two tasks and a waiver; c01's first bundle has a cover that
violates the policy and is repaired; c02 is the same item again, so it passes
on its own and is rejected at the set stage as a duplicate of c01.
"""

import json
import re
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
    p = propose.progress(before, {"c01": _res(kills=["m1", "m2"], holes=["h1", "h2", "w1"], reqs=["r1", "r2"]),
                                  "c02": _res(kills=["m2", "m3", "base_killed"])})
    m = p["mutants"]
    assert (m["baseline_survivors"], m["killed_by_plan"], m["killed_by_run"], m["remaining"]) == (3, 1, ["m2", "m3"], 0)
    # m1 was already killed by the plan; m2 is killed by both candidates, m3 only by c02.
    assert m["per_candidate"] == {"c01": {"kills": 1, "only_this_candidate": 0},
                                  "c02": {"kills": 2, "only_this_candidate": 1}}
    assert m["shared"] == {"m2": ["c01", "c02"]}
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
    (d / "multi.yaml").write_text("multi: []\n")  # an empty plan has no multi-target tasks
    for f in [*(d / "covers").glob("*.sv"), *(d / "gold").glob("*.sv"), *(d / "near_miss").glob("*.sv")]:
        f.unlink()
    return d


def survivor_answer(messages):
    """Pass 2: target the first survivor listed with a new task, call the rest unkillable."""
    ids = re.findall(r"^- (\S+:\d+:\w+:\d+)  \(", messages[0]["content"], re.M)
    unk = "\n".join(f'- {{mutant: "{m}", reason: "scripted"}}' for m in ids[1:])
    return (f"<candidates>\n- title: frame error a third time\n  kind: task\n  target_module: uart_rx\n"
            f"  behaviour: same again\n  why_baseline_misses: same\n  targets: [\"{ids[0]}\"]\n"
            f"  sources: [{{type: DOC, doc: pc16550d, page: 16}}]\n</candidates>\n<unkillable>\n{unk}\n</unkillable>\n")


def test_parse_survivor_answer():
    ok = ('<candidates>\n- {title: a, kind: task, targets: ["m1"]}\n</candidates>\n'
          '<unkillable>\n- {mutant: "m2", reason: "equivalent"}\n</unkillable>')
    cands, unk = propose.parse_survivor_answer(ok, ["m1", "m2"])
    assert cands[0]["targets"] == ["m1"] and unk == [{"mutant": "m2", "reason": "equivalent"}]
    for survivors, msg in [(["m1", "m2", "m3"], "not addressed: ['m3']"), (["m1"], "not remaining survivors: ['m2']")]:
        with pytest.raises(propose.ParseError, match=re.escape(msg)):
            propose.parse_survivor_answer(ok, survivors)
    both = ok.replace('mutant: "m2"', 'mutant: "m1"')
    with pytest.raises(propose.ParseError, match="both targeted and called unkillable"):
        propose.parse_survivor_answer(both, ["m1"])
    with pytest.raises(propose.ParseError, match="no targets"):
        propose.parse_survivor_answer(ok.replace('targets: ["m1"]', "x: 1"), ["m2"])


@needs_sim
def test_scripted_run_and_replay(scratch):
    bad_yaml = STAGE_A.replace("sources: [{type: DOC, doc: pc16550d, page: 16}]",
                               "sources: [{type: BASE, point: {name: prescale[4]}}]")
    def crash(messages):
        raise ConnectionError("interrupted")

    model = propose.ScriptedModel([bad_yaml, STAGE_A, r1_bundle("  initial $finish;\n"), r1_bundle(), r1_bundle(),
                                   survivor_answer, crash])
    ex = propose.Executor(image=None, j=8)
    run_dir = scratch / "run"
    # Interrupted in pass 2 Stage B; also lose one gate result and pass 1's set stage.
    with pytest.raises(ConnectionError):
        propose.run(run_dir, model, ex, base=empty_pack(scratch / "base"), survivor_pass=True)
    (run_dir / "gates/c01/1.json").unlink()
    shutil.rmtree(run_dir / "set")
    # Resume reuses every recorded response: exactly one new model call (c04 attempt 0).
    s = propose.resume(run_dir, propose.ScriptedModel([r1_bundle()]), ex)
    assert len(json.loads((run_dir / "manifest.json").read_text())["resumed"]) == 1
    p1, p2 = s["passes"]["1"], s["passes"]["2"]

    # Stage A: the first answer is not YAML; one repair turn fixes it.
    assert p1["stage_a"]["attempts"] == 2 and p1["stage_a"]["error"] is None
    rep = json.loads((run_dir / "responses/stage_a/1.json").read_text())["messages"][-1]["content"]
    assert "not valid YAML" in rep
    assert s["proposed"] == {"tasks": 3, "waivers": 1, "by_pass": {"1": 2, "2": 1}}
    assert [w["cid"] for w in s["waiver_proposals"]] == ["c03"]
    assert json.loads((run_dir / "gates/c01/0.json").read_text())["failed_gate"] == "cover_policy"
    assert p1["repair"] == {"failed_first_attempt": 1, "repaired": 1, "rate": 1.0}
    assert p1["rejected_at"] == {} and p1["rejected_at_set"] == {"c02": "duplicate"}
    assert p1["accepted"] == ["c01"] and s["accepted"] == ["c01"]
    assert s["cites_outside_context_pages"] == ["c02"]       # pc16550d p17 is not a context page
    first = {f["gate"]: f["passed"] for f in p1["funnel_first_attempt"]}
    assert (first["proposed"], first["cover_sync"], first["cover_policy"], first["duplicate"]) == (2, 2, 1, 1)
    nm = next(f for f in p1["funnel_final"] if f["gate"] == "near_miss")
    assert (nm["passed"], nm["opted_out"]) == (2, 0)
    assert s["hit_by_random"] == {"c01": {"rx": 101}}      # frame errors happen by accident
    prog = p1["progress"]                                   # base pack is empty: R1's effect is the run's
    assert prog["mutants"]["killed_by_plan"] == 0 and prog["mutants"]["killed_by_run"]
    assert "v_branch uart_rx.v:122 else" in prog["holes"]["closed_by_run"]
    assert prog["holes"]["waived"] == 48 and prog["requirements"]["cited_by_plan"] == 0
    assert len(prog["requirements"]["new_in_run"]) == 2
    repair = json.loads((run_dir / "responses/c01/1.json").read_text())["messages"][-1]["content"]
    assert "cover_policy" in repair and "initial is not allowed" in repair

    # Pass 2: sees the survivors pass 1 left; c04 (R1 again) passes alone, fails the set stage,
    # and its gold does not kill the survivor it claimed.
    sp = s["survivor_pass"]
    assert sp["remaining_before"] == prog["mutants"]["remaining"] and len(sp["unkillable"]) == sp["remaining_before"] - 1
    assert p2["rejected_at"] == {} and p2["rejected_at_set"] == {"c04": "duplicate"} and p2["accepted"] == []
    assert sp["targets_killed"] == {"c04": []}
    assert p2["progress"]["mutants"]["killed_by_plan"] == prog["mutants"]["killed_by_run"].__len__()
    assert s["progress_total"]["mutants"]["killed_by_run"] == prog["mutants"]["killed_by_run"]

    assert propose.replay(run_dir, ex) == []
    # --write-from refuses: the run gated against an empty pack, not designs/uart.
    assert propose.write_from(run_dir, ex) == ["designs/uart differs from the run's base_pack; re-run the proposer"]

    # Replay must notice a recorded decision it cannot reproduce.
    g = run_dir / "gates/c02/0.json"
    rec = json.loads(g.read_text())
    rec["accepted"] = False
    g.write_text(json.dumps(rec))
    assert "c02 attempt 0: gate result differs" in propose.replay(run_dir, ex)


def test_author_all_parallel(scratch):
    """Concurrent Stage B: each conversation stays under its own cid."""
    import threading
    import time

    class Echo:
        params = {"model": "echo", "temperature": 0, "max_tokens": 0}
        lock, live, peak = threading.Lock(), 0, 0

        def __call__(self, messages):
            with self.lock:
                self.live += 1
                self.peak = max(self.peak, self.live)
            time.sleep(0.05)
            with self.lock:
                self.live -= 1
            title = re.search(r"title: (t\d)", messages[0]["content"]).group(1)
            return {"text": f"no bundle for {title}", "finish_reason": "stop", "id": "e", "model": "e",
                    "usage": None, "seconds": 0}

    cands = [{"cid": f"c0{n}", "pass": 1, "title": f"t{n}", "kind": "task"} for n in range(1, 5)]
    model = Echo()
    propose.author_all(scratch, model, None, cands, "ctx", parallel=3)
    assert model.peak == 3
    for c in cands:
        files = sorted((scratch / "responses" / c["cid"]).glob("*.json"))
        assert len(files) == propose.RETRIES + 1
        assert all(json.loads(f.read_text())["response"]["text"] == f"no bundle for {c['title']}" for f in files)


# arm64 manifest of propose.IMAGE (the pipeline image), for local Docker on Apple silicon.
IMAGE_ARM = "docker.io/vishokjcs/closure-bench-toolchain@sha256:af43bde0ec76736914394e7cfb19a778b529c6c179475143fbf70cc3b407914f"


def _have_image() -> bool:
    import subprocess
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "image", "inspect", IMAGE_ARM], capture_output=True).returncode == 0


@pytest.mark.skipif(not _have_image(), reason="needs docker and the toolchain image (host only)")
def test_cache_save_parallel_containers():
    """-p runs gate containers at once; each is PID 1 and they share the mutation cache."""
    import subprocess
    d = propose.ROOT / ".cache" / "cache_race"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    try:
        code = ("import sys; from pathlib import Path; from closure_core.gates import save_cache\n"
                "for i in range(200): save_cache(Path('/repo/.cache/cache_race/c.json'), {sys.argv[1]: i})")
        procs = [subprocess.Popen(["docker", "run", "--rm", "--network", "none", "-v", f"{propose.ROOT}:/repo",
                                   "-w", "/repo", IMAGE_ARM, "python3", "-c", code, str(n)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in range(4)]
        errs = [p.communicate()[1] for p in procs]
        assert all(p.returncode == 0 for p in procs), errs
        assert len(json.loads((d / "c.json").read_text())) == 1
        assert not list(d.glob("*.tmp"))
    finally:
        shutil.rmtree(d, ignore_errors=True)
