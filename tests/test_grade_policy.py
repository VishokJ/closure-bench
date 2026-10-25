"""grade() enforces the testbench policy before simulating (tests/fixtures/attacks).

Each attack file's first line records what it scored before the policy was
enforced. Needs the pinned Verilator (toolchain image).
"""

from pathlib import Path

import pytest

from closure_core import grader, policy
from closure_core.design import find_repo_root, load_design

ROOT = find_repo_root()
ATTACKS = ROOT / "tests" / "fixtures" / "attacks"
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")


@pytest.fixture(scope="module")
def design():
    return load_design("uart")


@needs_sim
@pytest.mark.parametrize("name, reason", [
    ("force", "force is not allowed"),
    ("tb_hier_write", "hierarchical write into the design (dut.frame_error_reg)"),
    ("bind_hier_write", "hierarchical write into the design (uart_rx.frame_error_reg)"),
    ("bind_port", "placed inside module 'uart_rx'"),
    ("redefine_rtl", "redefines design or cover module 'uart_rx'"),
    ("redefine_cover", "redefines design or cover module 'cov_R1'"),
])
def test_attack_is_a_policy_violation(design, name, reason):
    g = grader.grade(design, ["R1"], (ATTACKS / f"{name}.sv").read_text())
    assert (g.status, g.reward, g.run_s) == ("policy_violation", 0.0, 0.0)
    assert reason in g.diagnostics


@needs_sim
def test_defparam_is_allowed(design):
    assert grader.check_policy(design, (ATTACKS / "defparam.sv").read_text()) == ([], "")


@needs_sim
def test_gold_and_baselines_pass_policy(design):
    assert grader.grade(design, ["R1"], (design.pack / "gold" / "R1.sv").read_text()).reward == 1.0
    for b in design.baselines.values():
        assert grader.check_policy(design, b["file"].read_text()) == ([], "")


@needs_sim
def test_unparseable_fails_closed(design):
    g = grader.grade(design, ["R1"], "module tb; this is not verilog; endmodule\n")
    assert (g.status, g.reward) == ("compile_error", 0.0)


def test_wrong_verilator_raises(design, monkeypatch):
    monkeypatch.setattr(policy, "verilator_version", lambda: "Verilator 5.052 2025-01-01")
    with pytest.raises(RuntimeError, match="needs Verilator 5.020"):
        grader.grade(design, ["R1"], "module tb; endmodule\n")
