"""Bash harness: the files setup puts in the agent's /workspace, and ./run.sh.

The run.sh tests need the pinned Verilator (toolchain image); they build the
workspace in a temp dir and run run.sh as the agent would.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

from closure_core import load_design, policy

ROOT = Path(__file__).resolve().parents[1]
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")


def _load(name):
    # Loaded by path: the adapter package needs verifiers, these modules do not.
    path = ROOT / f"environments/closure_bench/closure_bench/{name}.py"
    spec = importlib.util.spec_from_file_location(f"cb_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def p():
    return _load("prompt")


@pytest.fixture(scope="module")
def design():
    return load_design("uart")


def _agent_files(p, design) -> dict[str, bytes]:
    """Everything ClosureTask.setup writes in bash mode, minus the empty submission."""
    files = {k: v.encode() for k, v in p.visible_files(design).items()}
    files.update(p.workspace_tools(design, ["R1"], 60.0))
    return files


def test_agent_files_exclude_answers(p, design):
    files = _agent_files(p, design)
    assert not [r for r in files if "gold" in r.split("/") or "near_miss" in r.split("/")]
    answers = [*(design.pack / "gold").glob("*.sv"), *(design.pack / "near_miss").glob("*.sv")]
    assert answers
    for a in answers:
        body = a.read_bytes().strip()
        assert not [r for r, data in files.items() if body in data], a.name


def test_summary_format():
    s = _load("run_summary").summary
    ok = {"status": "ok", "target_hits": {"R1": 3}, "reward": 1.0, "diagnostics": ""}
    assert s(ok) == "status: ok\ntarget R1: 3 hits\nwould score: 1"
    pv = {"status": "policy_violation", "target_hits": {"R1": 0}, "reward": 0.0,
          "diagnostics": "tb.sv:7: force is not allowed"}
    assert s(pv).endswith("policy violations:\ntb.sv:7: force is not allowed")
    bad = {"status": "compile_error", "target_hits": {"R1": 0}, "reward": 0.0,
           "diagnostics": "%Error: syntax"}
    assert s(bad).endswith("log tail:\n%Error: syntax")


@pytest.fixture
def workspace(p, design, tmp_path):
    ws = tmp_path / "workspace"
    for rel, data in _agent_files(p, design).items():
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_bytes(data)
    (ws / p.RUN_SH).chmod(0o755)
    (ws / "submission").mkdir()
    return ws


def _run(ws: Path, tb_text: str) -> str:
    (ws / "submission" / "tb.sv").write_text(tb_text)
    # Relative path from the workspace, as the agent would call it.
    res = subprocess.run(["./run.sh", "submission/tb.sv"], cwd=ws,
                         capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    return res.stdout


@needs_sim
def test_run_sh_gold_scores(workspace, design):
    out = _run(workspace, (design.pack / "gold" / "R1.sv").read_text())
    assert out.startswith("status: ok\n")
    assert int(re.search(r"^target R1: (\d+) hits$", out, re.M).group(1)) > 0
    assert "would score: 1" in out


@needs_sim
def test_run_sh_empty_scores_0(workspace):
    out = _run(workspace, "")
    assert "target R1: 0 hits" in out and "would score: 0" in out


@needs_sim
def test_run_sh_reports_illegal_stimulus(workspace):
    """The workspace bundle carries the legality checker: run.sh stops illegal stimulus too."""
    out = _run(workspace, _illegal_tb())
    assert out.startswith("status: illegal_stimulus\n")
    assert "would score: 0" in out
    assert "ILLEGAL_STIMULUS: axis_tvalid_low_in_reset at " in out


def _illegal_tb() -> str:
    # s_axis_tvalid high during reset (AXI-Stream s2.8.2); tests/test_legality.py has the grader tests.
    return """`timescale 1ns / 1ps
module tb;
  logic clk = 1'b0;
  always #5 clk = ~clk;
  logic rst = 1'b1, s_axis_tvalid = 1'b1;
  logic [7:0] s_axis_tdata = 8'h55;
  logic [15:0] prescale = 16'd1;
  wire s_axis_tready, txd, busy;
  uart_tx dut (.*);
  initial begin
    repeat (3) @(negedge clk); rst = 1'b0;
    repeat (20) @(negedge clk); $finish;
  end
endmodule
"""


@needs_sim
def test_run_sh_reports_policy_violation(workspace):
    out = _run(workspace, (ROOT / "tests/fixtures/attacks/force.sv").read_text())
    assert out.startswith("status: policy_violation\n")
    assert "would score: 0" in out
    assert "policy violations:" in out and "force is not allowed" in out
