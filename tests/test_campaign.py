"""Campaign tasks: one per design module, up to max_files testbenches (default:
one per target), reward = fraction of the module's targets hit by at least one
file whose run is ok.

The grading tests need the pinned Verilator (toolchain image); they run
campaign.py's CLI on a submission directory, as the grade metric does.
"""

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from closure_core import load_design, policy

ROOT = Path(__file__).resolve().parents[1]
needs_sim = pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                               reason="needs the pinned Verilator (toolchain image)")
FORCE = ROOT / "tests/fixtures/attacks/force.sv"


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
def c(p):
    return p.campaign


@pytest.fixture(scope="module")
def design():
    return load_design("uart")


def _targets(p, design, module):
    return [it.id for it in design.plan
            if it.id in design.golds and p.module_of(design, it) == module]


def test_targets_per_module(p, design):
    rx, tx = _targets(p, design, "uart_rx"), _targets(p, design, "uart_tx")
    assert rx == [f"R{i}" for i in range(1, 12)]
    assert tx == ["T1", "T2", "T3", "T4"]


def test_eligible_keeps_pattern_and_size(c):
    sizes = {f"tb_{i:02d}.sv": 10 for i in range(10)}
    sizes |= {"tb.sv": 10, "tb_x.v": 10, "tb_a b.sv": 10, "notes.sv": 10, "tb_zero.sv": 0,
              "tb_big.sv": c.MAX_FILE_BYTES + 1, "tb_edge.sv": c.MAX_FILE_BYTES}
    assert c.eligible(sizes) == sorted([f"tb_{i:02d}.sv" for i in range(10)] + ["tb_edge.sv"])


def test_keep_drops_blank_files_before_the_cap(c):
    texts = {"tb_a.sv": " \n", "tb_b.sv": "module tb;", "tb_c.sv": "module tb;", "tb_d.sv": "x"}
    assert list(c.keep(texts, 2)) == ["tb_b.sv", "tb_c.sv"]


def test_combine_counts_only_ok_files(c):
    targets = ["R1", "R2", "R3"]
    res = {"tb_a.sv": {"status": "ok", "target_hits": {"R1": 2, "R2": 0, "R3": 0}},
           "tb_b.sv": {"status": "no_finish", "target_hits": {"R1": 0, "R2": 5, "R3": 0}},
           "tb_c.sv": {"status": "ok", "target_hits": {"R1": 1, "R2": 0, "R3": 0}}}
    g = c.combine(targets, res)
    assert g["target_hits"] == {"R1": 3, "R2": 0, "R3": 0}
    assert (g["targets_hit"], g["reward"], g["reward_kind"]) == (1, 1 / 3, "fraction")
    assert g["files"] == res


def test_extract_testbenches(p):
    reply = "```\n\n```\n" + "".join(
        f"```systemverilog\nmodule tb; // {i}\nendmodule\n```\n" for i in range(10))
    tbs = p.extract_testbenches(reply, 8)
    assert list(tbs) == [f"tb_{i}.sv" for i in range(1, 9)]  # the blank block takes no slot
    assert tbs["tb_1.sv"] == "module tb; // 0\nendmodule\n"
    assert p.extract_testbenches("no code", 8) == {}


def test_prompt_lists_every_target(p, design):
    items = [design.item(t) for t in _targets(p, design, "uart_rx")]
    for harness in ("null", "bash"):
        text = p.render_campaign(design, "uart_rx", items, 60.0, 11, harness)
        for it in items:
            assert f"### {it.id}\n\n{it.description}\n" in text
            assert f"point:  {it.cover}  (cover property in module {it.cover_module})" in text
        assert "/ 11. At most 11 testbenches are graded." in text
    assert "`./run.sh <file>...`" in p.render_campaign(design, "uart_rx", items, 60.0, 11, "bash")
    assert "up to 11 ```systemverilog code blocks" in p.system_prompt("null", 11)
    assert "Write up to 11 new SystemVerilog testbenches" in p.system_prompt("null", 11)
    assert "submission/tb_<name>.sv" in p.system_prompt("bash", 11)
    assert "{" not in p.system_prompt("bash", 11) and "{" not in p.system_prompt("bash")


def test_bundle_ships_campaign(p, design):
    assert p.grader_bundle(design)["campaign.py"] == (
        ROOT / "environments/closure_bench/closure_bench/campaign.py").read_bytes()


def _grade_dir(p, c, design, tmp_path, files: dict[str, Path], module="uart_rx",
               max_files: int | None = None) -> dict:
    """Install the grader bundle and grade a submission dir, as the grade metric does."""
    grader = tmp_path / "grader"
    for rel, data in p.grader_bundle(design).items():
        (grader / rel).parent.mkdir(parents=True, exist_ok=True)
        (grader / rel).write_bytes(data)
    sub = tmp_path / "submission"
    sub.mkdir()
    for name, src in files.items():
        shutil.copy(src, sub / name)
    targets = [a for t in _targets(p, design, module) for a in ("--target", t)]
    cap = ["--max-files", str(max_files)] if max_files else []
    res = subprocess.run(["python3", "campaign.py", "--design", "uart", *targets, *cap, "--dir", str(sub)],
                         cwd=grader, capture_output=True, text=True, timeout=1200)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@needs_sim
def test_one_gold_per_rx_target_scores_1(p, c, design, tmp_path):
    # Default cap: one file per target, so all 11 receiver golds are graded.
    g = _grade_dir(p, c, design, tmp_path, {f"tb_{t}.sv": design.golds[t]
                                            for t in _targets(p, design, "uart_rx")})
    assert len(g["files"]) == 11
    assert g["reward"] == 1.0 and g["targets_hit"] == 11 and g["reward_kind"] == "fraction"
    assert {f["status"] for f in g["files"].values()} == {"ok"}


@needs_sim
def test_cap_applies_after_dropping_blank_files(p, c, design, tmp_path):
    blank = tmp_path / "blank.sv"
    blank.write_text("\n  \n")
    g = _grade_dir(p, c, design, tmp_path, {"tb_0.sv": blank, "tb_1.sv": design.golds["R1"],
                                            "tb_2.sv": design.golds["R2"],
                                            "tb_3.sv": design.golds["R8"]}, max_files=2)
    assert list(g["files"]) == ["tb_1.sv", "tb_2.sv"]
    assert [t for t, h in g["target_hits"].items() if h] == ["R1", "R2"]


@needs_sim
def test_empty_submission_scores_0(p, c, design, tmp_path):
    g = _grade_dir(p, c, design, tmp_path, {})
    assert (g["reward"], g["files"]) == (0.0, {})


@needs_sim
def test_one_gold_scores_1_over_n(p, c, design, tmp_path):
    g = _grade_dir(p, c, design, tmp_path, {"tb_r1.sv": design.golds["R1"]})
    assert g["reward"] == 1 / 11
    assert [t for t, h in g["target_hits"].items() if h] == ["R1"]


@needs_sim
def test_force_file_ignored_and_recorded(p, c, design, tmp_path):
    # force.sv forces R1's frame error: before the policy it alone scored R1.
    g = _grade_dir(p, c, design, tmp_path, {"tb_force.sv": FORCE, "tb_r2.sv": design.golds["R2"]})
    assert g["files"]["tb_force.sv"]["status"] == "policy_violation"
    assert "force is not allowed" in g["files"]["tb_force.sv"]["diagnostics"]
    assert g["files"]["tb_r2.sv"]["status"] == "ok"
    assert g["target_hits"]["R1"] == 0
    assert g["reward"] == 1 / 11


@needs_sim
def test_run_sh_reports_across_files(p, design, tmp_path):
    ws = tmp_path / "workspace"
    for rel, data in p.workspace_tools(design, _targets(p, design, "uart_tx"), 60.0,
                                       max_files=4).items():
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_bytes(data)
    (ws / p.RUN_SH).chmod(0o755)
    (ws / "submission").mkdir()
    shutil.copy(design.golds["T1"], ws / "submission/tb_t1.sv")
    shutil.copy(FORCE, ws / "submission/tb_force.sv")
    res = subprocess.run(["./run.sh", "submission/tb_t1.sv", "submission/tb_force.sv"], cwd=ws,
                         capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "file submission/tb_t1.sv: ok, hits T1" in out
    assert "file submission/tb_force.sv: policy_violation" in out
    assert int(re.search(r"^target T1: (\d+) hits$", out, re.M).group(1)) > 0
    assert "target T2: 0 hits" in out and "would score: 1/4 = 0.25" in out
    assert "force is not allowed" in out
