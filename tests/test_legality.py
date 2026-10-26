"""Legal stimulus (closure_core/legality.py): one rule list, designs/uart/legality.yaml,
enforced by the grader (status illegal_stimulus) and assumed by formal.

Simulation tests need the pinned Verilator, formal tests the formal tools
(both: the pipeline image).
"""

import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from closure_core import citations, formal, gates, grader, legality, mutants, policy, sim
from closure_core.design import find_repo_root, load_design

ROOT = find_repo_root()
PACK = ROOT / "designs" / "uart"
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")
needs_formal = pytest.mark.skipif(not (formal.FORMAL_HOME / "bin" / "sby").exists(),
                                  reason="needs the formal tools (toolchain image)")

TX_HEAD = """`timescale 1ns / 1ps
module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'b1, s_axis_tvalid = 1'b0;
  logic [7:0] s_axis_tdata = 8'h55;
  logic [15:0] prescale = 16'd1;
  wire s_axis_tready, txd, busy;
  uart_tx dut (.*);
  initial begin
"""

# s_axis_tvalid rises one cycle into a three-cycle reset (AXI-Stream s2.8.2).
TVALID_IN_RESET = TX_HEAD + """\
    @(negedge clk); s_axis_tvalid = 1'b1;
    repeat (2) @(negedge clk); rst = 1'b0;
    repeat (200) @(negedge clk); $finish;
  end
endmodule
"""
# The same stimulus with s_axis_tvalid rising after reset: legal.
TVALID_AFTER_RESET = TVALID_IN_RESET.replace("@(negedge clk); s_axis_tvalid = 1'b1;\n    repeat (2) @(negedge clk); rst = 1'b0;",
                                             "repeat (3) @(negedge clk); rst = 1'b0; s_axis_tvalid = 1'b1;")

# rxd held low from a start bit (a break), so R1's frame error comes whatever the bit
# timing; prescale changes from 1 to 2 at CHANGE, 20 cycles into the frame (busy).
RX_BREAK = """`timescale 1ns / 1ps
module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'b1, rxd = 1'b1, m_axis_tready = 1'b1;
  logic [15:0] prescale = 16'd1;
  wire [7:0] m_axis_tdata;
  wire m_axis_tvalid, busy, overrun_error, frame_error;
  uart_rx dut (.*);
  initial begin
    repeat (2) @(negedge clk); rst = 1'b0;
    CHANGE_IDLE
    repeat (4) @(negedge clk); rxd = 1'b0;
    CHANGE_BUSY
    repeat (400) @(negedge clk); $finish;
  end
endmodule
"""
PRESCALE_WHILE_BUSY = RX_BREAK.replace("CHANGE_IDLE", "").replace(
    "CHANGE_BUSY", "repeat (20) @(negedge clk); if (!busy) $fatal(1, \"not busy\"); prescale = 16'd2;")
PRESCALE_WHILE_IDLE = RX_BREAK.replace("CHANGE_IDLE", "prescale = 16'd2;").replace("CHANGE_BUSY", "")

# prescale is 0 while uart_tx is idle (legal: never read), then 1 from the edge where
# s_axis_tvalid rises (PRESCALE); left 0 there it is illegal (the bit timer loads it).
PRESCALE_ZERO_IDLE = TX_HEAD.replace("prescale = 16'd1", "prescale = 16'd0") + """\
    repeat (3) @(negedge clk); rst = 1'b0;
    repeat (4) @(negedge clk); s_axis_tvalid = 1'b1; PRESCALE
    @(negedge clk); while (!s_axis_tready) @(negedge clk);  // handshake at the next edge
    @(negedge clk); s_axis_tvalid = 1'b0; prescale = 16'd1;
    repeat (200) @(negedge clk); prescale = 16'd0;
    repeat (4) @(negedge clk); $finish;
  end
endmodule
"""
# uart_rx loads its bit timer one edge after rxd falls (rxd_reg): a one-cycle low pulse
# on rxd with prescale 0 at that next edge is illegal, though rxd is high again there.
RXD_PULSE_ZERO = RX_BREAK.replace("CHANGE_IDLE", "").replace(
    "CHANGE_BUSY", "@(negedge clk); rxd = 1'b1; prescale = 16'd0; repeat (2) @(negedge clk); prescale = 16'd1;")

# uart_tx sends 8'h55 at prescale 1, loading it at the first edge after reset. prescale
# becomes 2 either at the falling edge right after that load edge (AT_START: busy as
# sampled at the next rising edge is 1, and the timer reloads from prescale later in
# the frame: illegal) or once busy is seen low again (AT_IDLE: busy sampled 0, prescale
# unread until the next start: legal). Old rule $past(busy) got both wrong.
PRESCALE_AT_BUSY_EDGE = TX_HEAD + """\
    repeat (3) @(negedge clk); rst = 1'b0;
    s_axis_tvalid = 1'b1;
    @(negedge clk); AT_START
    while (!s_axis_tready) @(negedge clk);
    @(negedge clk); s_axis_tvalid = 1'b0;
    AT_IDLE
    repeat (300) @(negedge clk); $finish;
  end
endmodule
"""


@pytest.fixture(scope="module")
def design():
    return load_design("uart")


def allowing(design, item_id, *rules):
    """The design with one plan item allowed to break `rules` (legality: {allow: [...]})."""
    plan = tuple(replace(it, legality_allow=rules) if it.id == item_id else it for it in design.plan)
    return replace(design, plan=plan)


# --- rules and generation: pure ------------------------------------------------------------------

def test_pack_rules_are_the_former_formal_assumptions(design):
    assert [r.id for r in design.legality.rules] == [
        "prescale_nonzero_rx", "prescale_nonzero_tx", "prescale_stable_while_busy", "axis_tvalid_low_in_reset",
        "axis_tvalid_held", "axis_tdata_stable"]
    # Search restrictions stay formal-only: none of them is a rule.
    assert not [r for r in design.legality.rules if "16'd4" in r.require or "init" in r.when]


def test_port_widths_match_the_formal_environment(design):
    """legality.yaml declares port widths for the checker; formal.yaml declares the same
    ports for the witness testbench. They must agree, or a checker port is truncated."""
    tops = yaml.safe_load((PACK / "formal" / "formal.yaml").read_text())["tops"]
    for module, ports in design.legality.ports.items():
        formal_ports = {"clk": 1, **tops[module]["inputs"], **tops[module]["outputs"]}
        assert {p: formal_ports[p] for p in ports} == ports, module


def test_allowed_rules_leave_both_texts(design):
    keep = legality.enforced(design.legality, [("prescale_stable_while_busy",)])
    assert "prescale_stable_while_busy" not in legality.checker_text(design.legality, keep)
    assert "prescale_stable_while_busy" not in "".join(t for t, _ in legality.assume_text(design.legality, keep).values())
    full = legality.checker_text(design.legality, design.legality.rules)
    assert "bind uart_rx chk_legal_uart_rx" in full and "bind uart_tx chk_legal_uart_tx" in full
    # A module with no rule left gets no checker at all.
    rx_only = legality.enforced(design.legality, [("prescale_nonzero_rx", "prescale_stable_while_busy")])
    assert "uart_rx" not in legality.checker_text(design.legality, rx_only)


def test_multi_target_enforces_what_any_target_forbids(design):
    d = allowing(design, "R1", "prescale_stable_while_busy")
    assert "prescale_stable_while_busy" not in [r.id for r in d.enforced(["R1"])]
    assert "prescale_stable_while_busy" in [r.id for r in d.enforced(["R1", "R2"])]
    assert d.enforced(["R2"]) == design.legality.rules


def test_unknown_allow_and_unknown_port_are_rejected(tmp_path):
    pack = shutil.copytree(PACK, tmp_path / "uart")
    plan = yaml.safe_load((pack / "plan.yaml").read_text())
    plan["items"][0]["legality"] = {"allow": ["no_such_rule"]}
    (pack / "plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
    with pytest.raises(ValueError, match="unknown rules"):
        load_design(pack)
    spec = yaml.safe_load((PACK / "legality.yaml").read_text())
    spec["rules"][0]["require"] = "prescal != 16'd0"
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(spec))
    with pytest.raises(ValueError, match="prescal"):
        legality.load(tmp_path / "bad.yaml")


def test_rule_citations_verify(design):
    if not all((citations.CACHE / f"{d}.pdf").exists() for d in ("axis",)):
        pytest.skip("axis.pdf not in the doc cache")
    r = gates.legality_citations(design, citations.DocStore(PACK, offline=True))
    assert r.ok is True, r.detail


# --- grader ----------------------------------------------------------------------------------

@needs_sim
def test_tvalid_during_reset_is_illegal(design):
    g = grader.grade(design, ["T1"], TVALID_IN_RESET)
    assert (g.status, g.reward) == ("illegal_stimulus", 0.0)
    assert legality.violations(g.diagnostics) == ["axis_tvalid_low_in_reset"]
    assert "ILLEGAL_STIMULUS: axis_tvalid_low_in_reset at " in g.diagnostics
    # Not vacuous: the same stimulus with s_axis_tvalid raised after reset is legal.
    assert grader.grade(design, ["T1"], TVALID_AFTER_RESET).status == "ok"


@needs_sim
def test_prescale_change_while_busy_is_illegal_unless_allowed(design):
    g = grader.grade(design, ["R1"], PRESCALE_WHILE_BUSY)
    assert (g.status, g.reward) == ("illegal_stimulus", 0.0)
    assert legality.violations(g.diagnostics) == ["prescale_stable_while_busy"]
    # The same testbench on an item that allows the hazard: legal, and it hits R1.
    d = allowing(design, "R1", "prescale_stable_while_busy")
    g = grader.grade(d, ["R1"], PRESCALE_WHILE_BUSY)
    assert (g.status, g.reward) == ("ok", 1.0), g.diagnostics
    # Grouped with an item that does not allow it, the rule holds again.
    assert grader.grade(d, ["R1", "R2"], PRESCALE_WHILE_BUSY).status == "illegal_stimulus"
    # Changing prescale while idle is legal anywhere.
    assert grader.grade(design, ["R1"], PRESCALE_WHILE_IDLE).reward == 1.0


@needs_sim
def test_prescale_zero_is_illegal_only_where_it_is_read(design):
    ok = grader.simulate(design, PRESCALE_ZERO_IDLE.replace("PRESCALE", "prescale = 16'd1;"))
    assert ok.sim.status == "ok", ok.sim.run_log
    bad = grader.simulate(design, PRESCALE_ZERO_IDLE.replace("PRESCALE", ""))
    assert bad.sim.status == "illegal_stimulus"
    assert legality.violations(bad.sim.run_log) == ["prescale_nonzero_tx"]
    pulse = grader.simulate(design, RXD_PULSE_ZERO)
    assert pulse.sim.status == "illegal_stimulus"
    assert legality.violations(pulse.sim.run_log) == ["prescale_nonzero_rx"]


@needs_sim
def test_prescale_stability_starts_and_ends_with_busy(design):
    """The rule follows busy as sampled at the edge: a change at the first idle edge
    after a frame is legal, a change right after the start edge is not."""
    idle = grader.simulate(design, PRESCALE_AT_BUSY_EDGE.replace("AT_START", "").replace(
        "AT_IDLE", "while (busy) @(negedge clk); prescale = 16'd2;"))
    assert idle.sim.status == "ok", idle.sim.run_log
    start = grader.simulate(design, PRESCALE_AT_BUSY_EDGE.replace(
        "AT_START", "if (!busy) $fatal(1, \"not busy\"); prescale = 16'd2;").replace("AT_IDLE", ""))
    assert start.sim.status == "illegal_stimulus"
    assert legality.violations(start.sim.run_log) == ["prescale_stable_while_busy"]


@needs_sim
def test_violation_at_the_finishing_edge_still_counts(design):
    """$finish at the edge of the violation: the checker runs in the same time step."""
    tb = TX_HEAD + """\
    @(negedge clk); s_axis_tvalid = 1'b1;
    @(posedge clk); $finish;
  end
endmodule
"""
    assert grader.grade(design, ["T1"], tb).status == "illegal_stimulus"


@needs_sim
def test_r1_gold_still_scores_one(design):
    g = grader.grade(design, ["R1"], (PACK / "gold" / "R1.sv").read_text())
    assert (g.status, g.reward) == ("ok", 1.0), g.diagnostics


@needs_sim
def test_checker_adds_no_coverage_points(design):
    s = grader.simulate(design, (PACK / "gold" / "R1.sv").read_text())
    assert s.sim.status == "ok"
    assert not [p for p in s.points if "chk_legal" in p.module or "/legal/" in p.file]


@needs_sim
def test_testbench_cannot_redefine_the_checker(design):
    tb = TVALID_AFTER_RESET + "module chk_legal_uart_tx (input logic clk); endmodule\n"
    g = grader.grade(design, ["T1"], tb)
    assert g.status == "policy_violation" and "chk_legal_uart_tx" in g.diagnostics


# --- mutation runs: no checker ---------------------------------------------------------------

def test_mutation_runs_compile_no_checker(design, monkeypatch):
    """Mutation status depends on RTL and testbench only (cache_key): the checker
    is left out, so cached results stay valid and a mutant that changes busy or
    s_axis_tready cannot turn a gold's run into illegal_stimulus."""
    compiled = []

    def build_and_run(work, sources, top, **kw):
        compiled.append([Path(s).name for s in sources])
        return sim.SimResult("compile_error", None, "", "", 0.0, 0.0, 1)

    monkeypatch.setattr(sim, "build_and_run", build_and_run)
    (path, (lo, hi)), = [(p, r) for p, r in design.mutate.items() if p.name == "uart_tx.v"]
    m = mutants.generate(path, lo, hi)[0]
    for mutant in (None, m):
        mutants.simulate(design, TVALID_IN_RESET, "tb", mutant)
    assert len(compiled) >= 2
    assert not [s for srcs in compiled for s in srcs if s == legality.CHECKER_FILE]
    # The grader itself does compile it.
    grader.simulate(design, TVALID_IN_RESET)
    assert legality.CHECKER_FILE in compiled[-1]


# --- formal: the same rules, as assumptions ---------------------------------------------------

def _probe(tmp_path, module, ports, cond):
    p = tmp_path / f"probe_{module}.sv"
    decl = ",\n".join(f"  input logic {w}{n}" for n, w in ports.items())
    p.write_text(f"module cov_P (\n{decl}\n);\n  P_probe: cover property (@(posedge clk) {cond});\n"
                 f"endmodule\nbind {module} cov_P u_cov_P (.*);\n")
    return p


@needs_formal
@needs_sim
@pytest.mark.parametrize("item", ["R1", "T1"])
def test_formal_witness_is_legal_by_construction(design, item):
    """Formal assumes every rule at every step, the last included, and the witness
    testbench only holds its last inputs after that: the checker never fires."""
    w = formal.cover_witness(PACK, PACK / "covers" / f"{item}.sv", bound=120, timeout=300,
                             minimize_timeout=60)
    assert w["status"] == "reachable"
    g = grader.grade(design, [item], w["tb_text"])
    assert (g.status, g.reward) == ("ok", 1.0), g.diagnostics


@needs_formal
@needs_sim
@pytest.mark.parametrize("rule, module, ports, cond", [
    ("axis_tvalid_low_in_reset", "uart_tx",
     {"clk": "", "rst": "", "s_axis_tvalid": ""}, "rst && s_axis_tvalid"),
    ("prescale_stable_while_busy", "uart_rx",
     {"clk": "", "busy": "", "prescale": "[15:0] "}, "busy && prescale != $past(prescale)"),
])
def test_formal_and_grader_agree_on_a_rule(design, tmp_path, rule, module, ports, cond):
    """A probe cover that is exactly a violation: unreachable under the rules, reachable
    once the rule is allowed, and that witness is what the grader calls illegal."""
    probe = _probe(tmp_path, module, ports, cond)
    assert formal.cover_witness(PACK, probe, bound=20, timeout=300)["status"] == "unreachable"
    w = formal.cover_witness(PACK, probe, bound=20, timeout=300, allow=(rule,))
    assert w["status"] == "reachable"
    s = grader.simulate(design, w["tb_text"])
    assert s.sim.status == "illegal_stimulus" and rule in legality.violations(s.sim.run_log)
    assert grader.simulate(design, w["tb_text"], rules=design.legality.rules[:0]).sim.status == "ok"


def test_witness_key_depends_on_the_allow_list(design):
    cover = (PACK / "covers" / "R1.sv").read_text()
    assert gates.witness_key(design, cover) != gates.witness_key(design, cover, ("prescale_nonzero_rx",))
    assert gates.witness_key(design, cover) == gates.witness_key(design, cover, ())
