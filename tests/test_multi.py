"""Multi-target tasks: multi.yaml validation and the prompt for several targets."""

import shutil

import pytest

from closure_core import load_design
from closure_core.design import find_repo_root

pytest.importorskip("verifiers")
from closure_bench import prompt  # noqa: E402


def test_multi_loads():
    d = load_design("uart")
    assert d.multi["M1"] == ("R1", "R2", "R3")
    assert all(set(ts) <= {it.id for it in d.plan} for ts in d.multi.values())


@pytest.mark.parametrize("bad", ["  - {id: R1, targets: [R2, R3]}",     # collides with a plan ID
                                 "  - {id: M9, targets: [R1]}",          # one target is not multi
                                 "  - {id: M9, targets: [R1, R99]}"])    # unknown target
def test_multi_rejects(tmp_path, bad):
    pack = tmp_path / "uart"
    shutil.copytree(find_repo_root() / "designs" / "uart", pack)
    (pack / "multi.yaml").write_text("multi:\n" + bad + "\n")
    with pytest.raises(ValueError, match="multi-target"):
        load_design(pack)


def test_multi_prompt_lists_every_target():
    d = load_design("uart")
    text = prompt.render(d, [d.item(t) for t in d.multi["M2"]], 60.0, task_id="M2")
    assert "## Targets: M2 (4 points; one testbench must hit all of them)" in text
    assert all(f"point:  {d.item(t).cover} " in text for t in d.multi["M2"])
    assert "every target point is hit" in text
