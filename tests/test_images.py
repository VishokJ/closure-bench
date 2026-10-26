"""Two images, kept apart: tasks run on the Verilator-only image, the pipeline on the
image that adds the formal tools. In the bash harness the agent has a shell in its
sandbox; with SymbiYosys there, closure would turn into running a model checker.

The docker checks need the images locally (host only) and skip otherwise.
"""

import re
import shutil
import subprocess
import tomllib

import pytest

from closure_core import propose
from closure_core.design import find_repo_root

ROOT = find_repo_root()
TASKSET = ROOT / "environments/closure_bench/closure_bench/taskset.py"
# Read, not imported: the adapter needs verifiers.
TASK_IMAGE = re.search(r'^DEFAULT_IMAGE = "([^"]+)"', TASKSET.read_text(), re.M).group(1)
CONFIGS = sorted((ROOT / "configs").glob("*.toml"))


def _images(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "image":
                yield v
            else:
                yield from _images(v)
    elif isinstance(node, list):
        for v in node:
            yield from _images(v)


def test_tasks_and_pipeline_use_different_images():
    assert TASK_IMAGE != propose.IMAGE


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.name)
def test_eval_configs_use_the_task_image(path):
    for image in _images(tomllib.loads(path.read_text())):
        assert image == TASK_IMAGE, f"{path.name}: {image}"


def _local(image):
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "image", "inspect", image], capture_output=True).returncode == 0


def _run(image, *argv):
    return subprocess.run(["docker", "run", "--rm", "--network", "none", image, *argv],
                          capture_output=True, text=True)


@pytest.mark.skipif(not _local(TASK_IMAGE), reason="needs docker and the task image locally")
def test_task_image_has_no_formal_tools():
    r = _run(TASK_IMAGE, "sh", "-c", "test ! -e /opt/oss-cad-suite && ! command -v yosys && ! command -v sby")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not (_local(TASK_IMAGE) and _local(propose.IMAGE)),
                    reason="needs docker and both images locally")
def test_same_verilator_in_both_images():
    task, pipe = (_run(i, "verilator", "--version") for i in (TASK_IMAGE, propose.IMAGE))
    assert task.returncode == pipe.returncode == 0
    assert task.stdout == pipe.stdout
    # The control: the pipeline image does have the formal tools.
    assert _run(propose.IMAGE, "test", "-x", "/opt/oss-cad-suite/bin/sby").returncode == 0
