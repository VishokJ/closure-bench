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


TWIN_GOOD = """module cov_ITEM_twin (
  input logic clk,
  input logic rst,
  input logic m_axis_tvalid
);
  ITEM_twin_good_stop: cover property (@(posedge clk) disable iff (rst) m_axis_tvalid);
endmodule

bind uart_rx cov_ITEM_twin u_cov_ITEM_twin (.*);
"""


# R1's cover reads one signal: with a twin it carries boundary; reset_timing is declared only.
STAGE_A_TARGET = STAGE_A.replace("  kind: task\n", "  kind: task\n  mechanism: [boundary, reset_timing]\n")


def target_bundle(twin: str | None = TWIN_GOOD) -> str:
    """R1's plan entry and cover without a gold (target-only mode), with an optional twin."""
    text = r1_bundle().replace("<plan>\n", "<plan>\nmechanism: [boundary, reset_timing]\n", 1)
    text = text[:text.index("<gold>")]
    return text + (f"<twin>\n{twin}</twin>\n" if twin else "")


@pytest.mark.parametrize("bad", [
    None,                                   # no mechanism
    "mechanism: [boundary, hard]",          # unknown name
    "mechanism: [boundary]",                # only one
    "mechanism: boundary",                  # only one, not a list
    "mechanism: [boundary, boundary]",      # not distinct
])
def test_parse_target_candidates_needs_two_mechanisms(bad):
    assert [c.get("mechanism") for c in propose.parse_target_candidates(STAGE_A_TARGET)] == \
        [["boundary", "reset_timing"]] * 2 + [None]  # waivers need none
    text = STAGE_A if bad is None else STAGE_A_TARGET.replace("mechanism: [boundary, reset_timing]", bad, 1)
    with pytest.raises(propose.ParseError, match="without a valid mechanism list"):
        propose.parse_target_candidates(text)


def test_set_stage_caps_reset_timing(scratch):
    """Three accepted candidates that list reset_timing: the set stage takes two, in cid order."""
    from test_gate_candidate import r1_candidate
    run_dir = scratch / "run"
    shutil.copytree(empty_pack(scratch / "base"), run_dir / "base_pack")
    cands = []
    for n in (1, 2, 3):
        cid, pid = f"c0{n}", f"P{n}"
        d = r1_candidate(run_dir / "candidates" / cid / "0", pid)
        item = yaml.safe_load((d / "item.yaml").read_text())
        (d / "item.yaml").write_text(yaml.safe_dump({**item, "mechanism": ["boundary", "reset_timing"]},
                                                    sort_keys=False))
        propose.dump(run_dir / "gates" / cid / "0.json", {"item": pid, "accepted": True, "gates": []})
        cands.append({"cid": cid, "pass": 1, "kind": "task"})
    propose.dump(run_dir / "candidates.json", {"passes": {"1": {"error": None}}, "candidates": cands})

    class Accept:
        def gate(self, cand, out, base=None, formal=None):
            res = {"item": yaml.safe_load((cand / "item.yaml").read_text())["id"], "accepted": True, "gates": []}
            propose.dump(out, res)
            return res

    propose.set_stage(run_dir, Accept())
    got = {c: json.loads((run_dir / "set" / f"{c}.json").read_text()) for c in ("c01", "c02", "c03")}
    assert [g["accepted"] for g in got.values()] == [True, True, False]
    assert got["c03"]["failed_gate"] == "reset_timing_cap"


def test_parse_bundle_target_only():
    b = propose.parse_bundle(target_bundle(), target_only=True)
    assert b["gold"] is None and b["near_miss"] == {} and "module cov_ITEM_twin" in b["twin"]
    assert propose.parse_bundle(target_bundle(None), target_only=True)["twin"] is None
    with pytest.raises(propose.ParseError, match="write no <gold>"):
        propose.parse_bundle(r1_bundle(), target_only=True)
    with pytest.raises(propose.ParseError, match="<gold>"):
        propose.parse_bundle(target_bundle())  # the default mode still needs a gold


def test_write_candidate_target_only(tmp_path):
    propose.write_candidate(propose.parse_bundle(target_bundle(), target_only=True), "P3", tmp_path / "c")
    assert not (tmp_path / "c" / "gold.sv").exists()
    twin = (tmp_path / "c" / "twin.sv").read_text()
    assert "module cov_P3_twin" in twin and "P3_twin_good_stop:" in twin and "u_cov_P3_twin" in twin


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
    ex = propose.Executor(image=None, j=2)
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


class SeedingExecutor(propose.Executor):
    """A local executor that plays the formal tool: before each gate it writes canned
    witnesses (by label suffix, e.g. 'frame_error') into the run's witness cache."""

    def __init__(self, witnesses: dict[str, dict]):
        super().__init__(image=None, j=2)
        self.witnesses = witnesses

    def gate(self, cand, out, base=None, formal=None):
        from closure_core import gates
        from closure_core.design import load_design
        design = load_design(base)
        covers = [(cand / "cover.sv", yaml.safe_load((cand / "item.yaml").read_text())["cover"])]
        if (cand / "twin.sv").is_file():
            covers.append((cand / "twin.sv", gates.twin_label(cand / "twin.sv")))
        formal["cache"].mkdir(parents=True, exist_ok=True)
        for cover, label in covers:
            if (w := self.witnesses.get(label.split("_", 1)[1])) is not None:
                gates.save_cache(formal["cache"] / f"{gates.witness_key(design, cover.read_text())}.json", w)
        return super().gate(cand, out, base, formal)


@needs_sim
def test_scripted_target_only_run_and_replay(scratch):
    """Target-only: c01's first twin is unreachable (repaired); c02 repeats c01 and is a set-stage
    duplicate; no survivor pass in this mode. Replay reuses the recorded witnesses."""
    fatal = 'if (!saw_frame_error) $fatal(1, "frame_error never pulsed");'
    stim = (PACK / "gold" / "R1.sv").read_text().replace(fatal, "")
    good = (PACK / "near_miss" / "R1_good_stop.sv").read_text()
    witnesses = {"frame_error": {"status": "reachable", "tb_text": stim, "depth": 120, "input_changes": 22},
                 "twin_bad": {"status": "unreachable"},
                 "twin_good_stop": {"status": "reachable", "tb_text": good, "depth": 121, "input_changes": 22}}
    bad = target_bundle(TWIN_GOOD.replace("twin_good_stop", "twin_bad"))
    model = propose.ScriptedModel([STAGE_A_TARGET, bad, target_bundle(), target_bundle()])
    run_dir = scratch / "run"
    base = empty_pack(scratch / "base")
    (base / "formal").mkdir(exist_ok=True)
    (base / "formal" / "formal.yaml").write_text("engine: abc bmc3\nbound: 300\ntimeout: 900\nminimize_timeout: 120\ntops: {}\n")
    (base / "formal" / "env_rx.sv").write_text("module formal_rx; endmodule\n")
    s = propose.run(run_dir, model, SeedingExecutor(witnesses), base=base, survivor_pass=True, target_only=True)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["target_only"] is True and manifest["survivor_pass"] is False
    assert manifest["min_frames"] is None
    # Target-only: no mutation sweep at startup; finish() measured the plan's progress instead.
    assert "progress_before" not in json.loads((run_dir / "context_pack.json").read_text())
    assert (run_dir / "progress_before.json").exists()

    prompt = json.loads((run_dir / "responses/c01/0.json").read_text())["messages"][0]["content"]
    assert "## Formal environment" in prompt and "### designs/uart/formal/env_rx.sv" in prompt
    assert "bound: 300" in prompt and "Do not write a gold" in prompt and "mechanism: [boundary, data]" in prompt
    a = json.loads((run_dir / "responses/stage_a/0.json").read_text())["messages"][0]["content"]
    assert "## Difficulty mechanism (this run)" in a
    assert s["mechanisms"] == {"boundary": ["c01"], "reset_timing": ["c01"]}
    first = json.loads((run_dir / "gates/c01/0.json").read_text())
    assert first["failed_gate"] == "formal"
    assert next(g for g in first["gates"] if g["gate"] == "mechanism")["ok"] is True
    repair = json.loads((run_dir / "responses/c01/1.json").read_text())["messages"][-1]["content"]
    assert "`formal`" in repair and "boundary not exact" in repair and "designs/uart/formal/" in repair

    assert list(s["passes"]) == ["1"]
    p1 = s["passes"]["1"]
    assert p1["accepted"] == ["c01"] and p1["rejected_at_set"] == {"c02": "duplicate"}
    assert p1["repair"] == {"failed_first_attempt": 1, "repaired": 1, "rate": 1.0}
    assert s["witnesses"] == {"c01": {"gold_source": "formal", "witness_depth": 120, "witness_frames": None,
                                      "active_frames": None, "input_changes": 22, "twin_depth": 121}}
    assert p1["progress"]["mutants"]["killed_by_run"] == []  # reach golds kill nothing
    # Keyed by the cover text, so per ID: P1 target, bad twin, good twin; P2 target and twin.
    assert len(list((run_dir / "formal").glob("*.json"))) == 5

    # A plain executor cannot solve (no closure_core.formal here): replay must use the record.
    assert propose.replay(run_dir, propose.Executor(image=None, j=2)) == []


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


RX_TOP = {"inputs": {"rst": 1, "rxd": 1, "m_axis_tready": 1, "prescale": 16},
          "outputs": {"m_axis_tdata": 8, "m_axis_tvalid": 1, "busy": 1, "overrun_error": 1, "frame_error": 1}}


def uart_witness(*stops: int, data: int = 0x55) -> dict:
    """A witness in formal.py's testbench format: reset, then one 8N1 frame per stop
    bit given (stop 0: a framing error), at prescale 1 (8 clocks per bit)."""
    from closure_core import formal
    steps = [{"rst": 1, "rxd": 1}] + [{"rst": 0, "rxd": 1}] * 3
    for stop in stops:
        bits = [0] + [(data >> i) & 1 for i in range(8)] + [stop, 1]
        steps += [{"rst": 0, "rxd": b} for b in bits for _ in range(8)]
    steps = [{**st, "m_axis_tready": 1, "prescale": 1} for st in steps]
    return {"status": "reachable", "tb_text": formal.witness_testbench(steps, RX_TOP, "uart_rx", "x"),
            "depth": len(steps), "input_changes": 1}


@needs_sim
def test_target_only_min_frames_repair(scratch):
    """--min-frames: a one-frame witness is rejected at formal, and the repair turn asks
    for more protocol activity; a two-frame target is then accepted."""
    deeper = target_bundle().replace("ITEM_frame_error: cover", "ITEM_frame_error_deep: cover") \
                            .replace("cover: ITEM_frame_error", "cover: ITEM_frame_error_deep")
    witnesses = {"frame_error": uart_witness(0), "frame_error_deep": uart_witness(1, 0),
                 "twin_good_stop": uart_witness(1)}
    one_task = STAGE_A_TARGET[:STAGE_A_TARGET.index("- title: frame error again")] + "</candidates>\n"
    model = propose.ScriptedModel([one_task, target_bundle(), deeper])
    base = empty_pack(scratch / "base")  # designs/uart/formal/formal.yaml: frame_cycles 80 * prescale
    run_dir = scratch / "run"
    s = propose.run(run_dir, model, SeedingExecutor(witnesses), base=base, target_only=True, min_frames=1.9)
    first = json.loads((run_dir / "gates/c01/0.json").read_text())
    assert first["failed_gate"] == "formal"
    repair = json.loads((run_dir / "responses/c01/1.json").read_text())["messages"][-1]["content"]
    assert "witness is 1.15 frames, below 1.9: make the target need more protocol activity" in repair
    assert s["passes"]["1"]["accepted"] == ["c01"]
    w = s["witnesses"]["c01"]
    assert (w["witness_depth"], w["witness_frames"]) == (180, 2.25)
    assert 1.5 < w["active_frames"] < 2.25  # two frames of activity in 2.25 frames (designs/uart formal.yaml)
    assert json.loads((run_dir / "manifest.json").read_text())["min_frames"] == 1.9
    assert propose.replay(run_dir, propose.Executor(image=None, j=2)) == []


@needs_sim
def test_infra_abort_is_not_a_decision(scratch):
    """A gate that fails on infrastructure (a simulation timing out twice) records nothing:
    the candidate is left out of the summary, replay and write refuse to treat it as a
    decision, and --resume gates it again. In the set stage the run stops instead, since
    later candidates are gated against the cumulative pack."""
    from closure_core.infra import InfraError

    class Flaky(propose.Executor):
        def __init__(self, fail_on):
            super().__init__(image=None, j=2)
            self.fail_on = fail_on  # "author" or "set": which stage's next gate fails

        def gate(self, cand, out, base=None, formal=None):
            stage = "set" if base and base.name == "setpack" else "author"
            if stage == self.fail_on:
                self.fail_on = None
                raise InfraError("simulation hit timeout twice")
            return super().gate(cand, out, base, formal)

    run_dir = scratch / "run"
    s = propose.run(run_dir, propose.ScriptedModel([STAGE_A, r1_bundle()]), Flaky("author"),
                    base=empty_pack(scratch / "base"), max_candidates=1)
    assert list(s["infra_aborted"]) == ["c01"] and s["accepted"] == [] and s["proposed"]["tasks"] == 0
    assert not (run_dir / "gates" / "c01").exists()
    assert propose.replay(run_dir, propose.Executor(image=None, j=2)) == []
    assert "the run has infrastructure aborts (infra/); --resume it first" in propose.write_from(run_dir, Flaky(None))

    # Resume reuses the recorded response (no model call); this time the set stage fails.
    with pytest.raises(InfraError):
        propose.resume(run_dir, propose.ScriptedModel([]), Flaky("set"))
    assert json.loads((run_dir / "gates/c01/0.json").read_text())["accepted"]
    assert json.loads((run_dir / "infra/c01.json").read_text())["stage"] == "set"
    assert not (run_dir / "summary.json").exists() and not (run_dir / "set" / "c01.json").exists()

    s = propose.resume(run_dir, propose.ScriptedModel([]), Flaky(None))
    assert s["infra_aborted"] == {} and s["accepted"] == ["c01"]
    assert [r["retried_infra"] for r in json.loads((run_dir / "manifest.json").read_text())["resumed"]] == [["c01"], ["c01"]]
    assert propose.replay(run_dir, propose.Executor(image=None, j=2)) == []
