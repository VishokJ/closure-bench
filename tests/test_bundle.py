"""The grading sandbox only gets prompt.grader_bundle(); it must be enough to load
the design, and it must not carry golds or near-misses."""

import importlib.util
from pathlib import Path

from closure_core import load_design

ROOT = Path(__file__).resolve().parents[1]


def _prompt():
    # Loaded by path: the adapter package needs verifiers, prompt.py does not.
    path = ROOT / "environments/closure_bench/closure_bench/prompt.py"
    spec = importlib.util.spec_from_file_location("cb_prompt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bundle_is_self_sufficient(tmp_path):
    design = load_design("uart")
    bundle = _prompt().grader_bundle(design)
    for rel, data in bundle.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(data)
    shipped = load_design("uart", repo_root=tmp_path)
    assert [it.id for it in shipped.plan] == [it.id for it in design.plan]
    assert len(shipped.covers) == len(design.covers)


def test_bundle_excludes_answers():
    bundle = _prompt().grader_bundle(load_design("uart"))
    assert not [r for r in bundle if "/gold/" in r or "/near_miss/" in r]
