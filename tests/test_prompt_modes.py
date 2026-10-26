"""The harness changes only how the agent reaches the files and the simulator:
null embeds the repo, bash lists /workspace and offers ./run.sh. Everything else
(target, report entry, description, toolchain facts, rules) is identical."""

import importlib.util
from pathlib import Path

import pytest

from closure_core import load_design

ROOT = Path(__file__).resolve().parents[1]


def _prompt():
    # Loaded by path: the adapter package needs verifiers, prompt.py does not.
    path = ROOT / "environments/closure_bench/closure_bench/prompt.py"
    spec = importlib.util.spec_from_file_location("cb_prompt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def p():
    return _prompt()


@pytest.fixture(scope="module")
def design():
    return load_design("uart")


def _render(p, design, harness):
    bash = harness == "bash"
    return p.render(design, design.item("R1"), 60.0, harness,
                    1200.0 if bash else None, 40 if bash else None)


def test_null_embeds_repo(p, design):
    text = _render(p, design, "null")
    for path, body in p.visible_files(design).items():
        assert f"### {path}\n" in text
        assert body.rstrip() in text
    assert "run.sh" not in text
    assert "```systemverilog code block" in p.system_prompt("null")


def test_bash_lists_workspace(p, design):
    text = _render(p, design, "bash")
    assert "## Repository" not in text
    for path, body in p.visible_files(design).items():
        assert f"- {path}\n" in text
        assert body.rstrip() not in text
    assert "`./run.sh <file>`" in text
    assert "submission/tb.sv" in text
    assert "limited to 1200 s and 40 model turns" in text
    assert "/workspace/submission/tb.sv" in p.system_prompt("bash")


def test_bash_limits_are_optional(p, design):
    item = design.item("R1")
    assert "limited to 1200 s. " in p.render(design, item, 60.0, "bash", 1200.0)
    assert "limited to" not in p.render(design, item, 60.0, "bash")


def test_shared_sections_identical(p, design):
    null = _render(p, design, "null").split("## Repository")[0]
    bash = _render(p, design, "bash").split("## Workspace")[0]
    assert null == bash
    assert "R1_frame_error" in null and "Verilator 5.020" in null


def test_system_prompts_differ_only_in_submit_rule(p, design):
    rules = design.enforced(["R1"])
    null, bash = (p.system_prompt(h, rules=rules).splitlines() for h in ("null", "bash"))
    diff = [(a, b) for a, b in zip(null, bash) if a != b]
    assert len(null) == len(bash) and len(diff) == 1
    assert diff[0][0].startswith("- Reply with") and diff[0][1].startswith("- Write")


def test_system_prompt_lists_the_enforced_legality_rules(p, design):
    text = p.system_prompt("null", rules=design.enforced(["R1"]))
    assert "- Drive legal stimulus only." in text and "illegal_stimulus" in text
    for r in design.legality.rules:
        assert f"  - {r.id} (" in text
    # An allowed rule is not listed: the agent sees exactly what its grade enforces.
    allowed = [r for r in design.legality.rules if r.id != "prescale_stable_while_busy"]
    assert "prescale_stable_while_busy" not in p.system_prompt("bash", rules=tuple(allowed))
