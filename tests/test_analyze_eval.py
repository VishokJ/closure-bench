"""tools/analyze_eval on a small synthetic run: Wilson and task-bootstrap
intervals, truncation, outcome categories, thinking-token split, run.sh calls,
grouping by max_tokens, calibration classes, determinism."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_loader = importlib.machinery.SourceFileLoader("analyze_eval", str(ROOT / "tools" / "analyze_eval"))
_spec = importlib.util.spec_from_loader("analyze_eval", _loader)
ae = importlib.util.module_from_spec(_spec)
_loader.exec_module(ae)


def trace(task, *, reward=0.0, status="ok", submission="module tb; endmodule",
          finish="stop", calls=1, source="reply", out_tokens=10, nodes=()):
    return {"task": {"data": {"id": task}}, "traces": [{
        "calls": [{"finish_reason": finish}] * calls,
        "rewards": {"target_reached": {"score": reward}},
        "metrics": {"turns": float(calls), "sim_seconds": 2.0},
        "info": {"submission": submission, "submission_source": source,
                 "grade": {"status": status}},
        "stop_condition": "agent_completed",
        "nodes": list(nodes),
        "num_total_tokens": 100 + out_tokens, "num_input_tokens": 100,
        "num_output_tokens": out_tokens,
    }]}


def write_run(d: Path, records, model="m/a", max_tokens=16000):
    (d / "configs" / "resolved").mkdir(parents=True)
    (d / "configs" / "resolved" / "eval.json").write_text(json.dumps({
        "model": model, "sampling": {"max_tokens": max_tokens},
        "env": {"taskset": {"harness": "null"}, "agent": {"harness": {"id": "null"}}}}))
    (d / "traces.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))


RECORDS = [
    trace("uart/R1", reward=1.0),                                      # hit
    trace("uart/R1", status="ok"),                                     # missed
    trace("uart/R1", status="compile_error"),                          # compile_error
    trace("uart/R1", status="policy_violation"),                       # policy_violation
    trace("uart/R2", status="timeout"),
    trace("uart/R2", status="runtime_error"),
    trace("uart/R2", status="no_finish"),
    # truncated: cut off mid-reply, nothing extracted; grader saw an empty file
    trace("uart/R2", status="compile_error", submission="", finish="length", source="none",
          out_tokens=500),
    # truncated: no model call at all (agent timeout before the first reply)
    trace("uart/R10", status="compile_error", submission="", calls=0, source="none",
          out_tokens=0),
    # infra: provider error, never graded
    {"task": {"data": {"id": "uart/R10"}}, "traces": [{"stop_condition": "provider_error",
                                                       "calls": [], "info": {}}]},
    {"task": {"data": {"id": "uart/R10"}}, "traces": []},
]


@pytest.fixture
def summary(tmp_path):
    write_run(tmp_path / "run_a", RECORDS)
    write_run(tmp_path / "run_b", [trace("uart/R1", reward=1.0)], max_tokens=32768)
    return ae.summarise(*ae.load([tmp_path]))


def test_wilson_known_values():
    assert ae.wilson(0, 0) is None
    lo, hi = ae.wilson(0, 4)
    assert lo == 0.0 and hi == pytest.approx(0.4899, abs=1e-4)
    lo, hi = ae.wilson(4, 4)
    assert lo == pytest.approx(0.5101, abs=1e-4) and hi == 1.0
    lo, hi = ae.wilson(5, 10)   # symmetric around 0.5
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)


def test_groups_split_by_max_tokens(summary):
    labels = [g["label"] for g in summary["groups"]]
    assert labels == ["m/a · null · max_tokens=16000", "m/a · null · max_tokens=32768"]


def test_outcome_categories(summary):
    g = summary["groups"][0]
    assert g["tasks"]["uart/R1"]["outcomes"] == {
        "no_submission": 0, "policy_violation": 1, "compile_error": 1, "timeout": 0,
        "runtime_error": 0, "no_finish": 0, "missed": 1, "hit": 1}
    r2 = g["tasks"]["uart/R2"]["outcomes"]
    assert (r2["timeout"], r2["runtime_error"], r2["no_finish"], r2["no_submission"],
            r2["compile_error"]) == (1, 1, 1, 1, 0)


def test_truncation_and_infra(summary):
    a = summary["groups"][0]["aggregate"]
    assert a["rollouts"] == 11 and a["infra_errors"] == 2 and a["graded"] == 9
    assert a["truncated"] == 2                       # finish_reason length + no call
    assert a["pass_at_1"] == pytest.approx(1 / 9, abs=1e-4)
    assert a["pass_at_1_untruncated"] == pytest.approx(1 / 7, abs=1e-4)
    assert "wilson95" not in a and a["bootstrap95"] is not None
    r10 = summary["groups"][0]["tasks"]["uart/R10"]
    assert (r10["graded"], r10["infra_errors"], r10["truncation_rate"]) == (1, 2, 1.0)
    assert r10["pass_at_1_untruncated"] is None


def test_task_order_is_natural(summary):
    assert list(summary["groups"][0]["tasks"]) == ["uart/R1", "uart/R2", "uart/R10"]


def test_outputs_deterministic(tmp_path, summary):
    outs = []
    for name in ("o1", "o2"):
        subprocess.run([sys.executable, str(ROOT / "tools" / "analyze_eval"), str(tmp_path),
                        "--out", str(tmp_path / name), "--no-charts"],
                       check=True, capture_output=True)
        outs.append({p.name: p.read_bytes() for p in sorted((tmp_path / name).iterdir())})
    assert outs[0] == outs[1]
    assert set(outs[0]) == {"summary.json", "tables.md", "calibration.json", "calibration.md"}


def test_bootstrap_resamples_tasks():
    assert ae.bootstrap_tasks([]) is None and ae.bootstrap_tasks([(0, 0)]) is None
    # one task: every resample is that task, so the interval has zero width
    assert ae.bootstrap_tasks([(3, 4)]) == (0.75, 0.75)
    # tasks at 4/4 and 0/4: resampled pooled rate is 0, 0.5 or 1 (1/4, 1/2, 1/4)
    assert ae.bootstrap_tasks([(4, 4), (0, 4)]) == (0.0, 1.0)
    many = [(k, 4) for k in (0, 1, 2, 3, 4, 4, 4, 2, 1, 0)]
    lo, hi = ae.bootstrap_tasks(many)
    assert ae.bootstrap_tasks(many) == (lo, hi)          # fixed seed
    assert 0 < lo < 21 / 40 < hi < 1


def test_thinking_tokens_split(summary):
    r2 = summary["groups"][0]["tasks"]["uart/R2"]
    assert r2["output_tokens_finished"] == {"mean": 10, "median": 10}
    assert r2["output_tokens_truncated"] == {"mean": 500, "median": 500}
    assert not r2["all_truncated"] and r2["truncation_rate"] == 0.25
    r10 = summary["groups"][0]["tasks"]["uart/R10"]
    # the no-reply rollout reports 0 tokens: excluded, counted separately
    assert r10["all_truncated"] and r10["no_reply"] == 1
    assert r10["output_tokens_truncated"] == {"mean": None, "median": None}
    assert summary["groups"][0]["aggregate"]["all_truncated_tasks"] == ["uart/R10"]


def test_run_sh_calls():
    def call(cmd):
        return {"type": "function", "function": {"name": "bash",
                                                 "arguments": json.dumps({"command": cmd})}}
    nodes = [{"message": {"role": "assistant", "content": "", "tool_calls": [
                 call("cat designs/uart/rtl/uart_rx.v"), call("./run.sh tb.sv")]}},
             {"message": {"role": "tool", "content": "run.sh: R1_frame_error hits 1"}},
             {"message": {"role": "assistant", "content": "I will use run.sh",
                          "tool_calls": [call("cd /workspace && ./run.sh submission/tb.sv")]}}]
    r = ae.classify(trace("uart/R1", nodes=nodes)["traces"][0])
    assert r["run_sh_calls"] == 2                         # tool output and prose do not count
    assert ae.classify(trace("uart/R1")["traces"][0])["run_sh_calls"] == 0


# --- calibration ------------------------------------------------------------

MID = [(2, 4), (1, 4), (3, 4), (2, 4), (2, 4), (1, 4), (3, 4), (2, 4), (2, 4), (3, 4)]


def calibration_for(tmp_path, counts, band=(0.3, 0.6)):
    """counts: {task: (hits, rollouts)} -> calibration of one synthetic run."""
    records = [trace(t, reward=float(i < k)) for t, (k, n) in counts.items() for i in range(n)]
    write_run(tmp_path / "run", records)
    groups, rollouts = ae.load([tmp_path])
    return ae.calibrate(ae.summarise(groups, rollouts), groups, band)["groups"][0]


def test_betainc_closed_forms():
    for x in (0.05, 0.2, 0.5, 0.9):
        assert ae.betainc(1, 1, x) == pytest.approx(x, abs=1e-12)
        assert ae.betainc(9, 1, x) == pytest.approx(x ** 9, abs=1e-12)
        assert ae.betainc(1, 9, x) == pytest.approx(1 - (1 - x) ** 9, abs=1e-12)
        assert ae.beta_ppf(ae.betainc(3, 5, x), 3, 5) == pytest.approx(x, abs=1e-9)


def test_two_of_two_among_mid_tasks_is_not_too_easy(tmp_path):
    counts = {f"uart/M{i}": c for i, c in enumerate(MID)} | {"uart/X": (2, 2)}
    g = calibration_for(tmp_path, counts)
    assert g["tasks"]["uart/X"]["class"] in ("unclear", "in_band")
    assert g["tasks"]["uart/M0"]["class"] == "in_band"          # 2/4 among mid tasks


def test_eight_of_eight_is_too_easy(tmp_path):
    # a probe-like set: some saturated, some unsolved, some mid tasks
    counts = ({f"uart/E{i}": (4, 4) for i in range(5)} | {f"uart/H{i}": (0, 4) for i in range(2)}
              | {f"uart/M{i}": c for i, c in enumerate(MID[:5])} | {"uart/X": (8, 8)})
    g = calibration_for(tmp_path, counts)
    assert g["tasks"]["uart/X"]["class"] == "too_easy"
    assert g["tasks"]["uart/X"]["p_gt_0.9"] > 0.8


def test_too_hard_and_unclear_rerun(tmp_path):
    counts = {f"uart/H{i}": (0, 8) for i in range(6)} | {f"uart/M{i}": c for i, c in enumerate(MID[:4])}
    g = calibration_for(tmp_path, counts)
    assert g["tasks"]["uart/H0"]["class"] == "too_hard"
    assert g["unclear"] and g["unclear"] == [t for t, r in g["tasks"].items()
                                             if r["class"] == "unclear"]
    cmd = g["rerun_command"]
    assert cmd.startswith("vf-eval @ ") and "/run/configs/eval.toml" in cmd
    assert "-m m/a --sampling.max_tokens 16000" in cmd
    assert f"--select.include.ids {' '.join(g['unclear'])} -r 2 -o " in cmd
    assert calibration_for(tmp_path / "all_easy", {"uart/E": (8, 8), "uart/F": (8, 8)})[
        "rerun_command"] is None


def test_prior_strength_capped_when_tasks_look_identical(tmp_path):
    # every task 2/4: the fit finds no spread and runs to the bound; the cap keeps
    # the prior at one task's worth of data, so a 4/4 task is not pulled to 0.5
    counts = {f"uart/M{i}": (2, 4) for i in range(10)} | {"uart/X": (4, 4)}
    g = calibration_for(tmp_path, counts)
    pr = g["prior"]
    assert pr["capped"] and pr["alpha"] + pr["beta"] == pytest.approx(4)
    assert g["tasks"]["uart/X"]["posterior_mean"] > 0.7


def test_set_level_band(tmp_path):
    g = calibration_for(tmp_path, {f"uart/M{i}": c for i, c in enumerate(MID)})
    st = g["set"]
    assert st["task_mean_pass_at_1"] == pytest.approx(0.525)
    assert st["bootstrap95"][0] <= 0.525 <= st["bootstrap95"][1]
    assert ae.band_verdict(st["bootstrap95"], (0.3, 0.6)) == st["verdict"]
    assert ae.band_verdict((0.4, 0.5), (0.3, 0.6)) == "in_band"
    assert ae.band_verdict((0.1, 0.2), (0.3, 0.6)) == "below"
    assert ae.band_verdict((0.7, 0.9), (0.3, 0.6)) == "above"
    assert ae.band_verdict((0.2, 0.5), (0.3, 0.6)) == "overlaps"
