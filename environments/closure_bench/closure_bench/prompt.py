"""What the agent sees: the repo an engineer would have, plus the coverage report
entry for the target and its one-line description.

Toolchain facts are stated (simulator, version, flags); solution hints are not.
The harness changes only how the agent reaches the files and the simulator:
null embeds the repo in the prompt (one reply, no tools); bash lists the files
in /workspace and offers ./run.sh, which runs the grader on a testbench.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from closure_core.design import Design, PlanItem
from closure_core.sim import VERILATOR_FLAGS

WORKDIR = "/workspace"
SUBMISSION = f"{WORKDIR}/submission/tb.sv"
RUN_SH = "run.sh"   # bash harness: the agent's coverage report, workspace-relative
TOOLS = ".tools"    # bash harness: grader bundle that run.sh calls

_SUBMIT_RULE = {
    "null": "Reply with exactly one ```systemverilog code block containing the complete testbench.",
    "bash": f"Write the complete testbench to {SUBMISSION}; that file is what is graded.",
}

_SYSTEM_TEMPLATE = """\
You are a hardware verification engineer doing coverage closure.

You are given an open-source design, its existing regression testbenches, the
functional coverage model, and a coverage report entry that has 0 hits. Write a
new SystemVerilog testbench that drives the design so the target coverage point
is hit.

Rules:
- {submit}
- The top-level module must be named `tb`.
- The testbench must end the simulation with $finish. A run that times out, stops
  without $finish, or ends with $fatal/$stop scores 0.
- Do not modify the design or the coverage model; only your testbench is used.
- Drive the design only through its ports, and instantiate it with its default
  parameters. A testbench that uses force/release, writes to signals inside the
  design, uses bind, redefines a design or coverage module, overrides a design
  parameter (#() or defparam), or calls $system, $c or file I/O is rejected
  before simulation and scores 0. Reading signals inside the design is allowed.
"""


def system_prompt(harness: str) -> str:
    return _SYSTEM_TEMPLATE.format(submit=_SUBMIT_RULE[harness])


def _cover_location(design: Design, item: PlanItem) -> str:
    for f in design.covers:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if re.match(rf"\s*{re.escape(item.cover)}\s*:", line):
                return f"covers/{f.name}:{n}"
    raise ValueError(f"cover {item.cover} not found")


def visible_files(design: Design) -> dict[str, str]:
    """Agent-visible repo: workspace-relative path -> contents."""
    files = {f"rtl/{p.name}": p.read_text() for p in design.rtl}
    files.update({f"baseline/{b['file'].name}": b["file"].read_text()
                  for b in design.baselines.values()})
    files.update({f"covers/{p.name}": p.read_text() for p in design.covers})
    return files


def _entry(design: Design, item: PlanItem) -> str:
    return (f"```\npoint:  {item.cover}  (cover property in module {item.cover_module})\n"
            f"source: {_cover_location(design, item)}\nhits:   0\n```\n")


def render(design: Design, items: PlanItem | list[PlanItem], run_timeout: float,
           harness: str = "null", agent_timeout: float | None = None,
           max_turns: int | None = None, task_id: str | None = None) -> str:
    """items: one target, or several (a multi-target task, task_id) that one testbench must all hit."""
    flags = " ".join(VERILATOR_FLAGS)
    items = [items] if isinstance(items, PlanItem) else items
    if len(items) == 1:
        item = items[0]
        sections = [f"## Target: {item.id}\n\n{item.description}\n",
                    "## Coverage report entry (baseline regression)\n\n" + _entry(design, item)]
        reward = "the target point is hit"
    else:
        sections = [f"## Targets: {task_id} ({len(items)} points; one testbench must hit all of them)\n"]
        for item in items:
            sections += [f"### {item.id}\n\n{item.description}\n",
                         "Coverage report entry (baseline regression):\n\n" + _entry(design, item)]
        reward = "every target point is hit"
    sections.append(
        "## How your testbench is run\n\n"
        "Compiled together with every file under rtl/ and covers/ using Verilator 5.020:\n"
        f"`verilator {flags} --top-module tb ...`\n"
        f"Simulation wall-clock limit: {int(run_timeout)} s. "
        f"Reward is 1 only if the run reaches $finish cleanly and {reward}.\n")
    if harness == "bash":
        sections.append(_workspace(design, agent_timeout, max_turns))
        return "\n".join(sections)
    sections.append("## Repository")
    for path, text in visible_files(design).items():
        lang = "verilog" if path.endswith(".v") else "systemverilog"
        sections.append(f"### {path}\n\n```{lang}\n{text.rstrip()}\n```\n")
    return "\n".join(sections)


def _workspace(design: Design, agent_timeout: float | None, max_turns: int | None) -> str:
    files = "".join(f"- {p}\n" for p in visible_files(design))
    text = (
        f"## Workspace\n\nYour files are in {WORKDIR}:\n\n{files}"
        f"- {RUN_SH}: `./{RUN_SH} <file>` compiles and simulates <file> exactly as described "
        "above, with our cover files, and prints the run status, the target's hits and "
        "whether it would score.\n"
        "- submission/tb.sv: empty. Write your final testbench here; only this file is "
        "graded, in a fresh sandbox.\n"
        f"- {TOOLS}/: the grader that {RUN_SH} calls.\n")
    limits = [f"{int(agent_timeout)} s" if agent_timeout is not None else "",
              f"{max_turns} model turns (one reply with its tool calls is one turn)"
              if max_turns is not None else ""]
    if any(limits):
        text += (f"\nYour session is limited to {' and '.join(l for l in limits if l)}. "
                 "Whatever submission/tb.sv holds when you stop or a limit is reached "
                 "is graded.\n")
    return text


CODE_BLOCK = re.compile(r"```(?:systemverilog|verilog|sv)?[ \t]*\n(.*?)```", re.S)


def extract_testbench(reply: str | None) -> str:
    """The last fenced code block in the reply; empty if there is none."""
    blocks = CODE_BLOCK.findall(reply or "")
    return blocks[-1].strip() + "\n" if blocks else ""


def grader_bundle(design: Design) -> dict[str, bytes]:
    """Files the grading sandbox needs, keyed by path relative to the bundle root.

    Mirrors the repo layout so closure_core.design.load_design works unchanged.
    Every pack-level YAML is shipped (design, plan, waivers, sources), so a new
    file referenced from design.yaml cannot silently break grading;
    tests/test_bundle.py checks that the bundle loads on its own. Golds and
    near-misses stay out, and so does formal.py: grading never uses it, and in
    the bash harness this bundle is the agent's workspace, where it would
    generate golds.
    """
    root = design.repo_root
    core = root / "closure_core"
    paths: list[Path] = [*(p for p in core.glob("*.py") if p.name != "formal.py"),
                         core / "sim_main.cpp",
                         *sorted(design.pack.glob("*.yaml")),
                         *design.rtl, *design.covers,
                         *(b["file"] for b in design.baselines.values()),
                         *(b["file"] for b in design.randoms.values())]  # load_design resolves them
    return {str(p.relative_to(root)): p.read_bytes() for p in paths}


def workspace_tools(design: Design, targets: list[str], run_timeout: float) -> dict[str, bytes]:
    """Bash harness: run.sh plus what it needs, keyed by workspace-relative path.

    run.sh runs the same grader CLI as the grading sandbox on the same bundle
    (so no golds or near-misses) and prints run_summary.py's short report. It
    is the reward function, by design; the grading sandbox still grades
    independently from its own copy.
    """
    files = {f"{TOOLS}/{rel}": data for rel, data in grader_bundle(design).items()}
    files[f"{TOOLS}/run_summary.py"] = Path(__file__).with_name("run_summary.py").read_bytes()
    target_args = " ".join(f"--target {shlex.quote(t)}" for t in targets)
    files[RUN_SH] = f"""\
#!/bin/sh
# ./{RUN_SH} <testbench.sv>: grade it as the grading sandbox will and print a summary.
set -e
[ $# -eq 1 ] || {{ echo "usage: ./{RUN_SH} <testbench.sv>" >&2; exit 2; }}
[ -f "$1" ] || {{ echo "{RUN_SH}: no such file: $1" >&2; exit 2; }}
tb=$(realpath "$1")
cd "$(dirname "$(realpath "$0")")/{TOOLS}"
out=$(python3 -m closure_core.grader \\
      --design {shlex.quote(design.name)} {target_args} --run-timeout {run_timeout} "$tb")
printf '%s\\n' "$out" | python3 run_summary.py
""".encode()
    return files
