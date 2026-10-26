"""closure_core.formal: cover translation for open-source Yosys, and witness -> testbench.

Translation tests are pure Python, plus a Yosys parse when the formal tools are
present. The R1 end-to-end test needs the formal tools and the pinned Verilator
(toolchain image): formal finds the witness, Verilator must score it 1.
"""

import re
import subprocess
from pathlib import Path

import pytest

from closure_core import formal, grader, policy
from closure_core.design import find_repo_root, load_design

ROOT = find_repo_root()
POLICY = ROOT / "tests" / "fixtures" / "policy"
COVERS = sorted((ROOT / "designs" / "uart" / "covers").glob("*.sv"))
# ok_vacuous.sv uses |->, which Verilator accepts but Yosys immediate covers do not.
SUPPORTED = [p for p in sorted(POLICY.glob("ok_*.sv")) + sorted(POLICY.glob("desc_*.sv")) + COVERS
             if p.name != "ok_vacuous.sv"]
needs_formal = pytest.mark.skipif(not (formal.FORMAL_HOME / "bin" / "sby").exists(),
                                  reason="needs the formal tools (toolchain image)")
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")


def test_translation_shape():
    text, binds = formal.translate_cover(
        "module cov_X (input logic clk, input logic rst, input logic e);\n"
        "  X_a: cover property (@(posedge clk) disable iff (rst) e && $past(e));\n"
        "endmodule\nbind uart_rx cov_X u_cov_X (.*);\n")
    assert "always @(posedge clk) if (!(rst)) X_a: cover (e && $past(e));" in text
    assert "bind" not in text and "property" not in text
    assert binds == [("uart_rx", "cov_X u_cov_X (.*);")]


@pytest.mark.parametrize("path", SUPPORTED, ids=lambda p: p.name)
def test_translation_keeps_labels_and_tracking(path):
    src = path.read_text()
    text, binds = formal.translate_cover(src)
    labels = re.findall(r"(\w+)\s*:\s*cover\s+property", src)
    assert labels and re.findall(r"(\w+)\s*:\s*cover\s*\(", text) == labels
    assert len(binds) == 1 and binds[0][0] in ("uart_rx", "uart_tx")
    # Tracking logic is copied unchanged: every always block of the source survives verbatim.
    for block in re.findall(r"always\s*@\(posedge clk\) begin.*?\n  end\n", src, re.S):
        assert block in text


@pytest.mark.parametrize("src, what", [
    ((POLICY / "bad_assert.sv").read_text(), "assert"),
    ((POLICY / "ok_vacuous.sv").read_text(), "|->"),
    ("module c(input clk, a, b);\n X: cover property (@(posedge clk) a ##1 b);\nendmodule\n"
     "bind uart_rx c u (.*);\n", "##"),
    ("module c(input clk, a);\n X: cover property (@(negedge clk) a);\nendmodule\n"
     "bind uart_rx c u (.*);\n", "posedge"),
])
def test_translation_rejects_unsupported(src, what):
    with pytest.raises(formal.UnsupportedCover, match=re.escape(what)):
        formal.translate_cover(src)


@needs_formal
@pytest.mark.parametrize("path", SUPPORTED, ids=lambda p: p.name)
def test_translation_parses_in_yosys(path, tmp_path):
    text, [(target, inst)] = formal.translate_cover(path.read_text())
    rtl = (ROOT / "third_party/verilog-uart/rtl" / f"{target}.v").read_text()
    (tmp_path / "rtl.v").write_text(formal._insert_instance(rtl, target, inst))
    (tmp_path / "cover.sv").write_text(text)
    r = subprocess.run([str(formal.FORMAL_HOME / "bin" / "yosys"), "-q", "-p",
                        f"read_verilog -formal -sv rtl.v cover.sv; prep -top {target}"],
                       cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@needs_formal
@needs_sim
def test_r1_witness_scores_one():
    design = load_design("uart")
    r = formal.cover_witness(design.pack, design.pack / "covers" / "R1.sv", bound=120, timeout=300)
    assert r["status"] == "reachable" and r["label"] == "R1_frame_error"
    assert r["depth"] <= 120 and r["input_changes"] >= 1
    g = grader.grade(design, ["R1"], r["tb_text"])
    assert (g.status, g.reward) == ("ok", 1.0), g.diagnostics


@needs_sim
def test_witness_testbench_replays_steps():
    """Conversion alone, from a hand-written R1 witness (no formal tools needed):
    reset for one cycle, then rxd held low through the stop bit at prescale 1."""
    design = load_design("uart")
    top = {"inputs": {"rst": 1, "rxd": 1, "m_axis_tready": 1, "prescale": 16},
           "outputs": {"m_axis_tdata": 8, "m_axis_tvalid": 1, "busy": 1,
                       "overrun_error": 1, "frame_error": 1}}
    steps = [{"rst": 1, "rxd": 1, "m_axis_tready": 1, "prescale": 1}]
    steps += [{"rst": 0, "rxd": 0, "m_axis_tready": 1, "prescale": 1}] * 90
    tb = formal.witness_testbench(steps, top, "uart_rx", "R1_frame_error")
    assert "module tb;" in tb and "$finish;" in tb and "@(negedge clk)" in tb
    g = grader.grade(design, ["R1"], tb)
    assert (g.status, g.reward) == ("ok", 1.0), g.diagnostics
    # The same trace with rxd idle never frames: the conversion is not vacuous.
    idle = [{**s, "rxd": 1} for s in steps]
    assert grader.grade(design, ["R1"], formal.witness_testbench(idle, top, "uart_rx", "R1")).reward == 0.0


# --- semantics that must match Verilator (--x-initial 0) ------------------------------------
# Probe covers bound to uart_rx. cover_witness takes any cover file; these never enter the plan.

def _probe(tmp_path, body, name="P_probe"):
    p = tmp_path / "probe.sv"
    p.write_text("module cov_P (input logic clk, input logic rst, input logic frame_error);\n"
                 f"{body}\n  {name}: cover property (@(posedge clk) disable iff (rst) hit);\n"
                 "endmodule\nbind uart_rx cov_P u_cov_P (.*);\n")
    return formal.cover_witness(ROOT / "designs" / "uart", p, bound=100, timeout=300)


@needs_formal
def test_unreset_register_starts_at_zero(tmp_path):
    """A register with no reset and no initializer must start at 0, as under Verilator
    --x-initial 0: holding its value, it can never be 1."""
    r = _probe(tmp_path, "  logic hit;\n  always @(posedge clk) hit <= hit;")
    assert r["status"] == "unreachable"


@needs_formal
def test_explicit_initializer_is_kept(tmp_path):
    """Control for the test above: an explicit initializer is honoured (hit at the first
    cycle out of reset), so the zero-init is not simply making everything unreachable.
    Depth 3: reset cycle, first cycle out of reset, the edge that samples the cover."""
    r = _probe(tmp_path, "  logic hit = 1'b1;\n  always @(posedge clk) hit <= hit;")
    assert r["status"] == "reachable" and r["depth"] == 3


@needs_formal
def test_sampled_functions_in_clocked_always(tmp_path):
    """$rose/$past inside a clocked always block (tracking registers, composed covers):
    the flag latches on the edge after frame_error rises, so its witness is exactly one
    cycle longer than R1's (frame_error itself)."""
    r1 = formal.cover_witness(ROOT / "designs" / "uart", ROOT / "designs/uart/covers/R1.sv",
                              bound=100, timeout=300)
    rose = _probe(tmp_path, "  logic hit;\n"
                  "  always @(posedge clk) if (rst) hit <= 0; else if ($rose(frame_error)) hit <= 1;")
    past = _probe(tmp_path, "  logic hit;\n"
                  "  always @(posedge clk) if (rst) hit <= 0;\n"
                  "    else if (frame_error && !$past(frame_error)) hit <= 1;")
    assert rose["depth"] == past["depth"] == r1["depth"] + 1


# --- k-induction (prove_unreachable) ----------------------------------------------------------

def _probe_file(tmp_path, body):
    p = tmp_path / "probe.sv"
    p.write_text("module cov_P (input logic clk, input logic rst, input logic rxd);\n"
                 f"{body}\n  P_probe: cover property (@(posedge clk) disable iff (rst) hit);\n"
                 "endmodule\nbind uart_rx cov_P u_cov_P (.*);\n")
    return p


@needs_formal
def test_prove_inductive_cover(tmp_path):
    p = _probe_file(tmp_path, "  logic hit;\n  always @(posedge clk) hit <= hit;")
    r = formal.prove_unreachable(ROOT / "designs" / "uart", p, timeout=300)
    assert (r["status"], r["k"]) == ("proven_unreachable", 1)


@needs_formal
def test_prove_inconclusive_stays_within_bound(tmp_path):
    """Unreachable but not k-inductive for any k: c counts 0..199 while rxd is high and
    wraps, so 250 is never reached; but from the unreachable state 200, c can stall
    (rxd low) for any number of cycles and then climb to 250. Induction cannot rule
    that out without an invariant, so the result must not claim a proof."""
    p = _probe_file(tmp_path, "  logic [7:0] c;\n  wire hit = c == 8'd250;\n"
                    "  always @(posedge clk) if (rst) c <= 0;\n"
                    "    else if (rxd) c <= (c == 8'd199) ? 8'd0 : c + 8'd1;")
    r = formal.prove_unreachable(ROOT / "designs" / "uart", p, ks=(1, 4, 16), timeout=300)
    assert r["status"] == "unreachable_within_bound" and r["k"] is None
