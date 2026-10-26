"""tools/regrade: re-grades info.submission from verifiers traces and reports changes."""

import json
import subprocess
import sys

import pytest

from closure_core import policy
from closure_core.design import find_repo_root

ROOT = find_repo_root()
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")


# s_axis_tvalid high during reset (axis_tvalid_low_in_reset).
TVALID_IN_RESET = """module tb;
  logic clk = 1'b0, rst = 1'b1, s_axis_tvalid = 1'b1;
  always #5 clk = ~clk;
  wire s_axis_tready, txd, busy;
  uart_tx dut (.clk, .rst, .s_axis_tdata(8'h55), .s_axis_tvalid, .s_axis_tready, .txd, .busy,
               .prescale(16'd1));
  initial begin
    repeat (3) @(negedge clk); rst = 1'b0;
    repeat (200) @(negedge clk); $finish;
  end
endmodule
"""


def record(task, targets, grade=None, submission=None):
    info = {} if grade is None else {"grade": grade, "submission": submission}
    return {"task": {"data": {"id": task, "design": "uart", "targets": targets}},
            "traces": [{"info": info}]}


@needs_sim
def test_regrade_reports_changed_outcomes(tmp_path):
    gold = (ROOT / "designs" / "uart" / "gold" / "R1.sv").read_text()
    recs = [record("uart/R1", ["R1"], {"status": "ok", "reward": 1.0}, gold),
            # recorded before the legality rules: illegal now
            record("uart/T1", ["T1"], {"status": "ok", "reward": 0.0}, TVALID_IN_RESET),
            record("uart/T1", ["T1"])]  # never graded (e.g. provider error)
    traces = tmp_path / "traces.jsonl"
    traces.write_text("".join(json.dumps(r) + "\n" for r in recs))
    out = tmp_path / "regrade.jsonl"
    res = subprocess.run([sys.executable, str(ROOT / "tools" / "regrade"), str(traces), "--out", str(out)],
                         capture_output=True, text=True, check=True)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [(r["status"], r["reward"]) for r in rows] == [("ok", 1.0), ("illegal_stimulus", 0.0), (None, None)]
    assert "3 rollouts, 2 graded, 1 changed" in res.stdout
