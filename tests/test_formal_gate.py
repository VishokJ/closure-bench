"""Formal gate (gold-less candidates), gold roles, twins and composed items.

Every test uses canned witnesses, written into the witness cache under the
key the gate computes, or a fake closure_core.formal, so no solver runs. The
simulation tests need the pinned Verilator (toolchain image): formal only
proposes the gold, Verilator still scores it.
"""

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml

from closure_core import candidate, formal, gates, propose
from closure_core.design import PlanItem, load_design

from test_gate_candidate import FATAL, PACK, empty_pack, gate_of, needs_sim, r1_candidate, run

ENV = "designs/uart/formal/"
ITEM = PlanItem("P1", "P1_frame_error", "cov_P1", "d", "T0")
KW = {"assumptions": ENV, "bound": 300}


@pytest.fixture(autouse=True)
def fresh_formal_version():
    """gates.formal_version() is cached per process. Tests here swap closure_core.formal
    for a fake; a version cached under the fake (None) would outlive the test and give
    later tests in the same xdist worker different witness keys than gate_candidate's."""
    gates.formal_version.cache_clear()
    yield
    gates.formal_version.cache_clear()


def add_formal_env(pack: Path, bound: int = 300, timeout: int = 900, frame_cycles: str | None = None,
                   active_signal: str | None = None) -> Path:
    """A minimal formal environment (the real one is designs/uart/formal/). frame_cycles
    only where a test needs frames: the canned witnesses elsewhere are not formal.py's."""
    (pack / "formal").mkdir(exist_ok=True)
    spec = {"engine": "abc bmc3", "bound": bound, "timeout": timeout, "minimize_timeout": 120,
            "tops": {"uart_rx": {"file": "env_rx.sv", "module": "formal_rx"}}}
    (pack / "formal" / "formal.yaml").write_text(yaml.safe_dump(
        spec | ({"frame_cycles": frame_cycles} if frame_cycles else {})
        | ({"active_signal": active_signal} if active_signal else {})))
    (pack / "formal" / "env_rx.sv").write_text("module formal_rx; endmodule\n")
    return pack


def reach(depth=100, changes=12, tb="module tb; initial $finish; endmodule\n"):
    return {"status": "reachable", "tb_text": tb, "depth": depth, "input_changes": changes, "detail": "",
            "key": "k" * 64}


# --- formal(): pure ---------------------------------------------------------------------

def test_formal_reachable_records_depth():
    r = gates.formal(ITEM, reach(), **KW)
    assert r.ok is True and r.data["gold_source"] == "formal"
    assert (r.data["witness_depth"], r.data["input_changes"]) == (100, 12)


@pytest.mark.parametrize("status, words", [
    ("unreachable", "is unreachable"), ("timeout", "timed out"),
    ("unsupported", "cannot translate"), ("invalid", "formal rejected"),
])
def test_formal_rejections_are_distinct(status, words):
    r = gates.formal(ITEM, {"status": status, "detail": "why", "key": "k"}, **KW)
    assert r.ok is False and words in r.detail and r.data["status"] == status
    if status in ("unreachable", "timeout"):
        assert ENV in r.detail  # the repair turn learns where the assumptions are


# --- witness length in frames: pure ---------------------------------------------------------

TOP = {"inputs": {"rst": 1, "rxd": 1, "m_axis_tready": 1, "prescale": 16},
       "outputs": {"m_axis_tdata": 8, "m_axis_tvalid": 1, "busy": 1, "overrun_error": 1, "frame_error": 1}}
FRAME = "80 * prescale"  # designs/uart/formal/formal.yaml


def trace(cycles: int, prescale: int, *, slow: int = 1) -> list[dict]:
    """A witness-shaped trace: reset, then rxd toggling every 8 bit-clocks; slow > 1
    repeats each step, i.e. the same stimulus at a `slow` times longer bit period."""
    steps = [{"rst": int(k == 0), "rxd": (k // 8) % 2, "m_axis_tready": 1, "prescale": prescale}
             for k in range(cycles)]
    return [s for s in steps for _ in range(slow)]


def frames(steps: list[dict]) -> float:
    tb = formal.witness_testbench(steps, TOP, "uart_rx", "P1_x")
    return gates.witness_frames(tb, len(steps), FRAME)


def test_frames_are_cycles_over_the_frame_length():
    assert frames(trace(80, 1)) == pytest.approx(1.0)
    assert frames(trace(156, 1)) == pytest.approx(1.95)
    assert frames(trace(80, 4)) == pytest.approx(0.25)


def test_a_slower_prescale_does_not_add_frames():
    """The smoke-run padding: the same witness at prescale 2 takes twice the cycles."""
    assert frames(trace(156, 2, slow=2)) == pytest.approx(frames(trace(156, 1)))
    assert len(trace(156, 2, slow=2)) == 312


def test_frames_follow_prescale_changes():
    steps = trace(40, 1) + trace(160, 4)          # 40/80 + 160/320
    assert frames(steps) == pytest.approx(1.0)


def test_frames_count_only_the_witness_cycles():
    """The testbench pads two cycles after the last step; depth decides what counts."""
    tb = formal.witness_testbench(trace(80, 1), TOP, "uart_rx", "P1_x")
    assert gates.witness_frames(tb, 40, FRAME) == pytest.approx(0.5)


def test_real_witness_measures_one_frame():
    tb = (Path(__file__).parent / "fixtures" / "formal" / "witness_R1.sv").read_text()
    assert gates.witness_frames(tb, 80, FRAME) == pytest.approx(1.0)  # R1 at prescale 1


@pytest.mark.parametrize("expr", ["80 * prescale ** 2", "__import__('os')", "80 * baud", "80.5 * prescale"])
def test_frame_formula_is_restricted(expr):
    with pytest.raises(ValueError, match="only integers"):
        gates.witness_frames(formal.witness_testbench(trace(8, 1), TOP, "uart_rx", "x"), 8, expr)


def test_frame_formula_must_be_positive():
    with pytest.raises(ValueError, match="is 0"):
        gates.witness_frames(formal.witness_testbench(trace(8, 0), TOP, "uart_rx", "x"), 8, FRAME)


def test_formal_min_frames():
    tb = formal.witness_testbench(trace(80, 1), TOP, "uart_rx", "P1_x")
    one = reach(depth=80, tb=tb)
    r = gates.formal(ITEM, one, **KW, min_frames=1.9, frame_cycles=FRAME)
    assert r.ok is False and r.detail == (
        "witness is 1.00 frames, below 1.9: make the target need more protocol activity (a further phase "
        "or an interaction), not more waiting or a slower prescale")
    assert (r.data["witness_depth"], r.data["witness_frames"]) == (80, 1.0)  # cycles still recorded
    two = reach(depth=156, tb=formal.witness_testbench(trace(156, 1), TOP, "uart_rx", "P1_x"))
    r = gates.formal(ITEM, two, **KW, min_frames=1.9, frame_cycles=FRAME)
    assert r.ok is True and "(1.95 frames)" in r.detail
    with pytest.raises(gates.FormalError, match="needs frame_cycles"):
        gates.formal(ITEM, one, **KW, min_frames=1.9)


def test_default_floor_accepts_two_frames_and_rejects_one():
    """--target-only's default: one-frame witnesses measure <= 1.05, two-frame ones >= 1.85
    (a transmitter target at prescale 1 then 3, rejected at the old 1.9)."""
    def gate(steps):
        tb = formal.witness_testbench(steps, TOP, "uart_rx", "P1_x")
        return gates.formal(ITEM, reach(depth=len(steps), tb=tb), **KW,
                            min_frames=propose.TARGET_MIN_FRAMES, frame_cycles=FRAME)
    assert propose.TARGET_MIN_FRAMES == 1.5
    assert gate(trace(84, 1)).ok is False                       # 1.05 frames
    assert gate(trace(80, 1) + trace(204, 3)).ok is True        # 1 + 204/240 = 1.85 frames


def test_unreadable_witness_is_an_infrastructure_error():
    with pytest.raises(gates.FormalError, match="cannot measure the witness in frames"):
        gates.formal(ITEM, reach(), **KW, frame_cycles=FRAME)  # not formal.py's testbench


def test_the_pack_states_its_frame_length():
    st = gates.formal_settings(load_design(PACK))
    assert (st["frame_cycles"], st["active_signal"]) == (FRAME, "busy")


# --- active_frames: a measurement (busy time in frames), never a decision ---------------------

def test_active_frames_from_probe_lines():
    log = "CBA 0 0 1\nCBA 4 1 1\nCBA 84 0 1\nCBA 100 1 4\nCBA_END\n"
    # busy 4..84 at prescale 1 (80/80) and 100..260 at prescale 4 (160/320)
    assert gates.active_frames_from_log(log, 260, "busy", FRAME) == pytest.approx(1.5)
    with pytest.raises(ValueError, match="incomplete"):
        gates.active_frames_from_log("CBA 0 0 1\n", 260, "busy", FRAME)


def test_probe_is_appended_before_endmodule():
    tb = formal.witness_testbench(trace(8, 1), TOP, "uart_rx", "x")
    probed = gates.active_probe(tb, 8, "busy", FRAME)
    assert probed.startswith(tb[:tb.rindex("endmodule")]) and probed.rstrip().endswith("endmodule")
    assert '$display("CBA %0d %0d %0d", cb_t, busy, prescale);' in probed


def one_frame(idle_after: int = 0) -> list[dict]:
    """Reset, one good 8N1 frame (0x55) at prescale 1, then idle_after cycles of line idle."""
    bits = [1] * 3 + [b for bit in [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1] for b in [bit] * 8] + [1] * idle_after
    return [{"rst": int(k == 0), "rxd": b, "m_axis_tready": 1, "prescale": 1} for k, b in enumerate([1] + bits)]


@needs_sim
def test_active_frames_ignore_waiting():
    """Idle cycles after the frame add witness frames but no active frames."""
    d = load_design(PACK)
    got = {}
    for idle in (0, 80):
        steps = one_frame(idle)
        w = {"tb_text": formal.witness_testbench(steps, TOP, "uart_rx", "x"), "depth": len(steps)}
        got[idle] = (gates.witness_frames(w["tb_text"], w["depth"], FRAME),
                     gates.active_frames(d, w, FRAME, "busy")["active_frames"])
    assert got[80][0] == pytest.approx(got[0][0] + 1.0)
    assert got[80][1] == got[0][1] and 0.9 < got[0][1] < 1.0, got


def test_formal_twin():
    assert gates.formal(ITEM, reach(), reach(depth=99), **KW).data["twin"]["witness_depth"] == 99
    r = gates.formal(ITEM, reach(), {"status": "unreachable", "key": "t"}, **KW)
    assert r.ok is False and "boundary not exact" in r.detail
    r = gates.formal(ITEM, reach(), {"status": "timeout", "key": "t"}, **KW)
    assert r.ok is False and "timed out" in r.detail and "twin" in r.detail
    r = gates.formal(ITEM, reach(), twin_violations=["x.sv:1: initial is not allowed"], **KW)
    assert r.ok is False and "twin.sv: policy" in r.detail


def test_formal_not_needed_with_own_gold():
    r = gates.formal(ITEM, None)
    assert r.ok == "n/a" and r.data["gold_source"] == "llm"


def test_reach_gold_header_marks_the_role(tmp_path):
    g = tmp_path / "g.sv"
    g.write_text(gates.reach_gold_text(reach(depth=87), 300))
    assert g.read_text().splitlines()[0] == gates.REACH_HEADER and "depth 87" in g.read_text()
    assert gates.gold_source(g) == "formal"
    g.write_text("module tb; endmodule\n// gold_source: formal\n")
    assert gates.gold_source(g) == "llm"  # only the first line counts


# --- solve_witness against a fake closure_core.formal: pure -----------------------------

class UnsupportedCover(ValueError):
    pass


def fake_formal(monkeypatch, behaviour, during=None):
    """behaviour: a witness, an exception, or a list of them (one per call).
    during(): runs inside each call; its results are appended to the calls."""
    calls = []
    script = list(behaviour) if isinstance(behaviour, list) else None

    def cover_witness(pack_dir, cover_file, *, bound, timeout, engine, minimize_timeout):
        calls.append((Path(pack_dir), Path(cover_file), bound, timeout, engine, minimize_timeout))
        if during:
            calls.append(during())
        b = script.pop(0) if script is not None else behaviour
        if isinstance(b, Exception):
            raise b
        return b

    mod = types.SimpleNamespace(cover_witness=cover_witness, UnsupportedCover=UnsupportedCover)
    monkeypatch.setitem(sys.modules, "closure_core.formal", mod)
    return calls


@pytest.fixture
def pack(tmp_path):
    return load_design(add_formal_env(empty_pack(tmp_path / "pack"), bound=300, timeout=900))


def test_solve_passes_pack_cover_bound_and_timeout(pack, tmp_path, monkeypatch):
    calls = fake_formal(monkeypatch, {**reach(), "label": "P1_x", "solve_s": 1.0})
    cover = tmp_path / "c.sv"
    cover.write_text("x")
    w = gates.witness(pack, cover, tmp_path / "w")
    assert calls == [(pack.pack, cover, 300, 900.0, "abc bmc3", 120.0)]  # all from formal.yaml
    assert w["status"] == "reachable" and w["label"] == "P1_x"  # extra keys are kept
    gates.witness(pack, cover, tmp_path / "w")
    assert len(calls) == 1  # cached


@pytest.mark.parametrize("exc, status", [(UnsupportedCover("##"), "unsupported"), (ValueError("2 covers"), "invalid")])
def test_cover_errors_are_cached_rejections(pack, tmp_path, monkeypatch, exc, status):
    fake_formal(monkeypatch, exc)
    cover = tmp_path / "c.sv"
    cover.write_text("x")
    w = gates.witness(pack, cover, tmp_path / "w")
    assert w["status"] == status and str(exc) in w["detail"]
    assert len(list((tmp_path / "w").glob("*.json"))) == 1


def test_shared_store_hit_is_copied_into_the_run(pack, tmp_path, monkeypatch):
    """A witness another run solved is reused without solving, and the run keeps a copy."""
    calls = fake_formal(monkeypatch, reach())
    cover, run, store = tmp_path / "c.sv", tmp_path / "run", tmp_path / "store"
    cover.write_text("x")
    w = gates.witness(pack, cover, tmp_path / "other_run", store)
    assert len(calls) == 1 and [p.stem for p in store.glob("*.json")] == [w["key"]]
    assert gates.witness(pack, cover, run, store) == w and len(calls) == 1  # from the store
    assert json.loads((run / f"{w['key']}.json").read_text()) == json.loads((store / f"{w['key']}.json").read_text())
    (store / f"{w['key']}.json").unlink()
    assert gates.witness(pack, cover, run, store) == w and len(calls) == 1  # the run's copy, for replay


def test_shared_store_skips_timeouts_and_keeps_entries(pack, tmp_path, monkeypatch):
    fake_formal(monkeypatch, [{"status": "timeout"}, {"status": "timeout"}, reach()])
    cover, store = tmp_path / "c.sv", tmp_path / "store"
    cover.write_text("x")
    assert gates.witness(pack, cover, tmp_path / "run1", store)["status"] == "timeout"
    assert not list(store.glob("*.json"))  # machine- and load-dependent: never shared
    w = gates.witness(pack, cover, tmp_path / "run2", store)  # another run solves it again
    assert w["status"] == "reachable" and len(list(store.glob("*.json"))) == 1
    assert not gates.store_witness(store, w["key"], {"status": "unreachable"})  # never overwritten
    assert json.loads((store / f"{w['key']}.json").read_text())["status"] == "reachable"


def test_witness_store_is_split_by_the_engine(tmp_path):
    import hashlib
    engine = (Path(gates.__file__).with_name("formal.py")).read_bytes()
    assert gates.witness_store(tmp_path) == tmp_path / hashlib.sha256(engine).hexdigest()[:16]


def other_process_can_solve(lock: Path) -> bool:
    """Can another process take the formal lock shared right now (start a solve)?"""
    probe = ("import fcntl, sys\nf = open(sys.argv[1], 'a+')\n"
             "try:\n    fcntl.lockf(f, fcntl.LOCK_SH | fcntl.LOCK_NB)\nexcept OSError:\n    sys.exit(1)")
    return subprocess.run([sys.executable, "-c", probe, str(lock)]).returncode == 0


def test_formal_timeout_is_retried_alone(pack, tmp_path, monkeypatch):
    """A first timeout may be load: retried once while no other formal job can run,
    and only the retry's outcome is cached."""
    cover, cache = tmp_path / "c.sv", tmp_path / "w"
    cover.write_text("x")
    calls = fake_formal(monkeypatch, [{"status": "timeout"}, reach()],
                        during=lambda: other_process_can_solve(cache / ".formal.lock"))
    w = gates.witness(pack, cover, cache)
    assert w["status"] == "reachable" and w["retried"] is True
    assert [c for c in calls if isinstance(c, bool)] == [True, False]  # shared, then exclusive
    assert [json.loads(f.read_text())["status"] for f in cache.glob("*.json")] == ["reachable"]


def test_formal_timeout_twice_is_a_cached_rejection(pack, tmp_path, monkeypatch):
    cover, cache = tmp_path / "c.sv", tmp_path / "w"
    cover.write_text("x")
    calls = fake_formal(monkeypatch, [{"status": "timeout"}, {"status": "timeout"}])
    w = gates.witness(pack, cover, cache)
    assert (w["status"], w["retried"], len(calls)) == ("timeout", True, 2)
    assert gates.witness(pack, cover, cache) == w and len(calls) == 2  # cached: replay reuses it
    r = gates.formal(ITEM, w, **KW)
    assert r.ok is False and r.detail.startswith(
        "target too hard to verify within the time budget: simplify one mechanism or reduce depth")
    res = {"failed_gate": "formal", "gates": [{"gate": "formal", "ok": False, "detail": r.detail, "data": r.data}]}
    assert gates.TIMEOUT_DETAIL in propose.repair_message(res)  # what the proposer's repair turn sees


def test_infrastructure_errors_abort_and_are_not_cached(pack, tmp_path, monkeypatch):
    cover = tmp_path / "c.sv"
    cover.write_text("x")
    fake_formal(monkeypatch, RuntimeError("sby failed"))
    with pytest.raises(gates.FormalError, match="sby failed"):
        gates.witness(pack, cover, tmp_path / "w")
    monkeypatch.setitem(sys.modules, "closure_core.formal", None)  # import fails
    with pytest.raises(gates.FormalError, match="unavailable"):
        gates.witness(pack, cover, tmp_path / "w")
    assert not list((tmp_path / "w").glob("*.json"))  # only the formal lock file


def test_formal_settings_come_from_formal_yaml(tmp_path):
    none = empty_pack(tmp_path / "none")
    shutil.rmtree(none / "formal")  # designs/uart has one
    with pytest.raises(gates.FormalError, match="engine, bound, timeout and minimize_timeout"):
        gates.formal_settings(load_design(none))
    d = load_design(add_formal_env(empty_pack(tmp_path / "p"), bound=123, timeout=45))
    assert gates.formal_settings(d) == {"engine": "abc bmc3", "bound": 123, "timeout": 45.0,
                                        "minimize_timeout": 120.0, "frame_cycles": None, "active_signal": None}


def test_witness_key_covers_the_whole_formal_folder(pack):
    k = gates.witness_key(pack, "cover")
    assert gates.witness_key(pack, "cover ") != k
    (pack.pack / "formal" / "env_rx.sv").write_text("module formal_rx; /* changed */ endmodule\n")
    k2 = gates.witness_key(pack, "cover")
    assert k2 != k
    (pack.pack / "formal" / "formal.yaml").write_text("bound: 301\ntimeout: 900\n")
    assert gates.witness_key(pack, "cover") != k2


def test_witness_key_includes_the_tools_version(pack, monkeypatch):
    monkeypatch.setattr(gates, "formal_version", lambda: "Yosys 0.58")
    a = gates.witness_key(pack, "cover")
    monkeypatch.setattr(gates, "formal_version", lambda: "Yosys 0.59")
    assert gates.witness_key(pack, "cover") != a


# `yosys -V` in the two manifests of the pipeline image (OSS CAD Suite 2026-10-09).
YOSYS_ARM64 = "Yosys 0.69+272 (git sha1 230fb23f8, Release, GNU /usr/bin/aarch64-linux-gnu-g++ 15.2.0)"
YOSYS_X86_64 = "Yosys 0.69+272 (git sha1 230fb23f8, Release, Clang /usr/bin/clang++ 21.1.8)"


def test_witness_key_is_the_same_on_arm64_and_x86_64(pack, monkeypatch):
    keys = {}
    for arch, v in {"arm64": YOSYS_ARM64, "x86_64": YOSYS_X86_64,
                    "other revision": YOSYS_X86_64.replace("230fb23f8", "230fb23f9")}.items():
        monkeypatch.setattr(gates, "formal_version", lambda v=v: v)
        keys[arch] = gates.witness_key(pack, "cover")
    assert keys["arm64"] == keys["x86_64"] != keys["other revision"]
    assert gates.tools_release(YOSYS_ARM64) == "Yosys 0.69+272 (git sha1 230fb23f8)"
    assert gates.tools_release("yosys, some other format") == "yosys, some other format"


# --- format, value and composed near-misses: pure ---------------------------------------

def test_format_rejects_reach_header_in_own_gold(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    (cand / "gold.sv").write_text(gates.REACH_HEADER + "\n" + (cand / "gold.sv").read_text())
    r = candidate.check_format(cand, set())
    assert r.ok is False and "reserved for formal witnesses" in r.detail


def test_format_composed_from_must_name_plan_items(tmp_path):
    cand = r1_candidate(tmp_path / "c")
    item = yaml.safe_load((cand / "item.yaml").read_text())
    (cand / "item.yaml").write_text(yaml.safe_dump({**item, "composed_from": ["R1", "R99"]}))
    assert candidate.check_format(cand, {"R1"}).ok is False
    (cand / "item.yaml").write_text(yaml.safe_dump({**item, "composed_from": ["R1"]}))
    assert candidate.check_format(cand, {"R1"}).ok is True


def test_plan_composed_from_is_loaded_and_checked(tmp_path):
    d = shutil.copytree(PACK, tmp_path / "p")
    plan = yaml.safe_load((d / "plan.yaml").read_text())
    r1 = next(x for x in plan["items"] if x["id"] == "R1")
    r1.update(composed_from=["R2"], template="count")
    (d / "plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
    it = load_design(d).item("R1")
    assert (it.composed_from, it.template) == (("R2",), "count")
    r1["composed_from"] = ["R99"]
    (d / "plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
    with pytest.raises(ValueError, match="composed_from"):
        load_design(d)


def test_value_inherits_component_requirements():
    req = {"type": "README", "role": "requirement", "file": "README.md", "lines": [1, 2], "anchor": "a"}
    rtl = {"type": "RTL", "file": "x.v", "lines": [1, 1], "anchor": "b"}
    assert gates.value([], [], [(rtl, True)]).ok is False
    r = gates.value([], [], [(rtl, True)], {"R1": [(req, True)], "R8": [(req, False)]})
    assert r.ok is True and r.data["evidence"] == "spec" and r.data["inherited_from"] == ["R1"]
    assert r.data["requirement_keys"] == []  # not a new requirement citation of this item
    assert "(from R1)" in r.detail


def sim(**hits):
    return types.SimpleNamespace(plan_hits=hits)


@pytest.mark.parametrize("template, b_hit, golds", [
    ("cross", 0, ["gold:A", "gold:B"]), ("seq", 0, ["gold:A", "gold:B"]), ("count", 0, ["gold:A"]),
    ("excl", 1, ["gold:A"]), ("excl", 0, []), ("budget", 0, []),
])
def test_composed_near_misses_by_template(template, b_hit, golds):
    comps = ("A",) if template == "count" else ("A", "B")
    it = PlanItem("P1", "P1_x", "cov_P1", "d", "T3", composed_from=comps, template=template)
    sims = {"gold:A": sim(A=1, B=b_hit), "gold:B": sim(B=1), "near_miss:A_late.sv": sim(A=0)}
    if template == "count":
        del sims["gold:B"]
    assert [n for n, _ in gates.composed_near_misses(it, sims)] == golds + ["near_miss:A_late.sv"]


# --- full gate runs ---------------------------------------------------------------------

def stimulus() -> str:
    """R1's gold stimulus without its check: what a witness looks like."""
    g = (PACK / "gold" / "R1.sv").read_text()
    assert FATAL in g
    return g.replace(FATAL, "")


TWIN = """module cov_P1_twin (
  input logic clk,
  input logic rst,
  input logic m_axis_tvalid
);
  P1_twin_good_stop: cover property (@(posedge clk) disable iff (rst) m_axis_tvalid);
endmodule

bind uart_rx cov_P1_twin u_cov_P1_twin (.*);
"""

WITNESS = {"status": "reachable", "depth": 120, "input_changes": 22, "detail": ""}


def seed(cache: Path, base: Path, cand: Path, by_label: dict[str, dict]):
    """Write canned witnesses under the keys the gate will compute for cand's covers."""
    design = load_design(base)
    label = yaml.safe_load((cand / "item.yaml").read_text())["cover"]
    covers = [(cand / "cover.sv", label)]
    if (cand / "twin.sv").is_file():
        covers.append((cand / "twin.sv", gates.twin_label(cand / "twin.sv")))
    cache.mkdir(parents=True, exist_ok=True)
    for cover, lab in covers:
        if lab in by_label:
            gates.save_cache(cache / f"{gates.witness_key(design, cover.read_text())}.json", by_label[lab])


def gold_less(tmp_path: Path, by_label: dict[str, dict], twin: str | None = None, keep_near_miss=True,
              frame_cycles: str | None = None, active_signal: str | None = None, **kw) -> dict:
    cand = r1_candidate(tmp_path / "c")
    (cand / "gold.sv").unlink()
    if not keep_near_miss:
        shutil.rmtree(cand / "near_miss")
    if twin:
        (cand / "twin.sv").write_text(twin)
    base = add_formal_env(empty_pack(tmp_path / "base"), frame_cycles=frame_cycles, active_signal=active_signal)
    seed(tmp_path / "witnesses", base, cand, by_label)
    return run(tmp_path, cand, base, witness_cache=tmp_path / "witnesses", **kw)


@needs_sim
def test_gold_less_r1_is_accepted_with_a_reach_gold(tmp_path):
    res = gold_less(tmp_path, {"P1_frame_error": {**WITNESS, "tb_text": stimulus()}})
    assert res["accepted"], res
    assert [g["gate"] for g in res["gates"]] == candidate.ORDER
    f = gate_of(res, "formal")
    assert f["ok"] is True and (f["data"]["witness_depth"], f["data"]["input_changes"]) == (120, 22)
    assert f["data"]["bound"] == 300  # from formal.yaml
    assert gate_of(res, "gold")["data"]["gold_source"] == "formal"  # passed without a $fatal
    v = gate_of(res, "value")["data"]
    assert v["evidence"] == "spec" and v["kills"] == []  # a reach gold never kills a mutant


@needs_sim
def test_unreachable_is_rejected(tmp_path):
    res = gold_less(tmp_path, {"P1_frame_error": {"status": "unreachable", "detail": ""}})
    assert res["failed_gate"] == "formal", res
    assert ENV in gate_of(res, "formal")["detail"]
    assert res["skipped"] == candidate.ORDER[candidate.ORDER.index("formal") + 1:]


@needs_sim
def test_without_formal_tools_the_gate_aborts(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "closure_core.formal", None)
    with pytest.raises(gates.FormalError):
        gold_less(tmp_path, {})


@needs_sim
def test_twin_that_hits_the_target_is_rejected(tmp_path):
    w = {**WITNESS, "tb_text": stimulus()}
    res = gold_less(tmp_path, {"P1_frame_error": w, "P1_twin_good_stop": w}, twin=TWIN, keep_near_miss=False)
    assert res["failed_gate"] == "near_miss", res
    assert "P1_twin.sv" in gate_of(res, "near_miss")["detail"]


@needs_sim
def test_twin_that_misses_is_the_near_miss(tmp_path):
    t = {**WITNESS, "tb_text": (PACK / "near_miss" / "R1_good_stop.sv").read_text(), "depth": 121}
    res = gold_less(tmp_path, {"P1_frame_error": {**WITNESS, "tb_text": stimulus()}, "P1_twin_good_stop": t},
                    twin=TWIN, keep_near_miss=False)
    assert res["accepted"], res
    assert gate_of(res, "formal")["data"]["twin"]["witness_depth"] == 121
    assert "P1_twin.sv" in gate_of(res, "near_miss")["data"]["overlap"]


@needs_sim
def test_min_frames_rejects_a_one_frame_witness(tmp_path):
    """End to end with R1's real formal witness (one frame at prescale 1)."""
    tb = (Path(__file__).parent / "fixtures" / "formal" / "witness_R1.sv").read_text()
    w = {"P1_frame_error": {**WITNESS, "depth": 80, "tb_text": tb}}
    res = gold_less(tmp_path / "a", w, frame_cycles=FRAME, active_signal="busy", min_frames=1.9)
    assert res["failed_gate"] == "formal"
    assert gate_of(res, "formal")["detail"].startswith("witness is 1.00 frames, below 1.9")
    assert gate_of(res, "formal")["data"]["active_frames"] == 0.963  # recorded on rejections too
    res = gold_less(tmp_path / "b", w, frame_cycles=FRAME, min_frames=0.9)
    assert res["accepted"], res["failed_gate"]
    assert gate_of(res, "formal")["data"]["witness_frames"] == 1.0


@needs_sim
def test_composed_item_whose_component_gold_hits_it_fails_near_miss(tmp_path):
    """cross(R1, ...) that is really just R1: R1's gold, inherited as a near-miss, hits it."""
    cand = r1_candidate(tmp_path / "c")
    item = yaml.safe_load((cand / "item.yaml").read_text())
    (cand / "item.yaml").write_text(yaml.safe_dump({**item, "composed_from": ["R1"], "template": "cross"},
                                                   sort_keys=False))
    res = run(tmp_path, cand, PACK)
    assert res["failed_gate"] == "near_miss", res
    assert "gold:R1" in gate_of(res, "near_miss")["detail"]


# --- real formal (pipeline image: formal tools + pinned Verilator) ----------------------

def _have_formal() -> bool:
    try:
        from closure_core import formal
    except ImportError:
        return False
    return (formal.FORMAL_HOME / "bin" / "sby").exists()


needs_formal = pytest.mark.skipif(not _have_formal(), reason="needs the formal tools (pipeline image)")


@needs_sim
@needs_formal
def test_real_formal_gold_less_r1(tmp_path, monkeypatch):
    """End to end: cover_witness finds R1's witness, Verilator scores it 1, every gate passes;
    gating again reuses the cached witness instead of re-solving."""
    cand = r1_candidate(tmp_path / "c")
    (cand / "gold.sv").unlink()
    base = empty_pack(tmp_path / "base")
    assert (base / "formal" / "formal.yaml").is_file()  # the real environment
    res = run(tmp_path, cand, base, witness_cache=tmp_path / "witnesses")
    assert res["accepted"], res
    f = gate_of(res, "formal")["data"]
    assert f["status"] == "reachable" and f["bound"] == 300 and f["witness_depth"] > 0
    assert gate_of(res, "gold")["data"]["gold_source"] == "formal"
    assert len(list((tmp_path / "witnesses").glob("*.json"))) == 1

    monkeypatch.setattr(gates, "solve_witness", lambda *a: pytest.fail("re-solved a cached witness"))
    (tmp_path / "again").mkdir()
    assert run(tmp_path / "again", cand, base, witness_cache=tmp_path / "witnesses") == res


@needs_sim
@needs_formal
def test_real_formal_unreachable_cover(tmp_path):
    """frame_error and overrun_error on one clock: set in exclusive branches (uart_rx.v:123-128)."""
    cand = r1_candidate(tmp_path / "c")
    (cand / "gold.sv").unlink()
    c = (cand / "cover.sv").read_text()
    c = c.replace("  input logic frame_error\n", "  input logic frame_error,\n  input logic overrun_error\n")
    (cand / "cover.sv").write_text(c.replace("disable iff (rst) frame_error)", "disable iff (rst) frame_error && overrun_error)"))
    base = empty_pack(tmp_path / "base")
    res = run(tmp_path, cand, base, witness_cache=tmp_path / "witnesses")
    assert res["failed_gate"] == "formal", res
    assert gate_of(res, "formal")["data"]["status"] == "unreachable"


# --- mechanism (needs Verilator's parse) ------------------------------------------------

SEQ_COVER = """module cov_P1 (
  input logic clk,
  input logic rst,
  input logic frame_error,
  input logic [7:0] m_axis_tdata,
  input logic m_axis_tvalid
);
  logic seen;
  always @(posedge clk) if (rst) seen <= 1'b0; else if (frame_error) seen <= 1'b1;
  P1_frame_error: cover property (@(posedge clk) disable iff (rst) seen && m_axis_tvalid && m_axis_tdata == 8'h55);
endmodule

bind uart_rx cov_P1 u_cov_P1 (.*);
"""


def mech(tmp_path, mechanism, cover=None, twin=False, required=False):
    cand = r1_candidate(tmp_path / "c")
    if cover:
        (cand / "cover.sv").write_text(cover)
    candidate.overlay(empty_pack(tmp_path / "base"), cand, tmp_path / "o")
    d = load_design(tmp_path / "o")
    raw = {} if mechanism is None else {"mechanism": mechanism}
    return gates.mechanism(d, d.item("P1"), raw, twin, None, required)


@needs_sim
@pytest.mark.parametrize("mechanism, cover, twin, ok, words", [
    (None, None, False, False, "declare mechanism"),
    ("hard", None, False, False, "must each be one of"),
    ("boundary", None, False, False, "needs a twin"),
    ("boundary", None, True, True, ""),
    ("sequence", None, False, False, "tracking register"),
    ("interaction", None, False, False, "reads ['frame_error']"),
    ("data", None, False, False, "multi-bit constant"),
    ("reset_timing", None, False, True, ""),
    ("sequence", SEQ_COVER, False, True, ""),
    ("interaction", SEQ_COVER, False, True, ""),
    ("data", SEQ_COVER, False, True, ""),
])
def test_mechanism_is_checked(tmp_path, mechanism, cover, twin, ok, words):
    """Each mechanism's rule, whenever one is declared (one is enough outside target-only)."""
    r = mech(tmp_path, mechanism, cover, twin, required=mechanism is None)
    assert r.ok is ok and words in r.detail, r


@needs_sim
@pytest.mark.parametrize("mechanism, cover, twin, ok, words", [
    ("boundary", None, True, False, "combine at least 2 distinct"),
    (["boundary"], None, True, False, "combine at least 2 distinct"),
    (["boundary", "boundary"], None, True, False, "lists one twice"),
    (["boundary", "reset_timing"], None, True, True, "boundary, reset_timing"),
    # Every failing mechanism in one message, so one repair turn can fix them all.
    (["boundary", "interaction", "data"], None, False, False,
     "needs a twin cover (twin.sv) for the off-by-one condition; interaction needs"),
    (["sequence", "interaction", "data"], SEQ_COVER, False, True, "sequence, interaction, data"),
])
def test_target_only_needs_two_mechanisms(tmp_path, mechanism, cover, twin, ok, words):
    r = mech(tmp_path, mechanism, cover, twin, required=True)
    assert r.ok is ok and words in r.detail, r
    assert ok is False or r.data["mechanisms"] == mechanism


@needs_sim
def test_mechanism_optional_outside_target_only(tmp_path):
    assert mech(tmp_path, None, required=False).ok == "n/a"
