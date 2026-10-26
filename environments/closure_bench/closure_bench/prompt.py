"""What the agent sees: the repo an engineer would have, plus the coverage report
entry for the target and its one-line description.

Toolchain facts are stated (simulator, version, flags); solution hints are not.
The harness changes only how the agent reaches the files and the simulator:
null embeds the repo in the prompt (one reply, no tools); bash lists the files
in /workspace and offers ./run.sh, which runs the grader on a testbench.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path

from closure_core.design import Design, PlanItem
from closure_core.sim import VERILATOR_FLAGS

# By path, not `from closure_bench import campaign`: the package pulls in verifiers,
# which the toolchain image (where this module is tested) does not have.
_spec = importlib.util.spec_from_file_location("closure_bench_campaign",
                                               Path(__file__).with_name("campaign.py"))
campaign = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(campaign)

WORKDIR = "/workspace"
SUBMISSION = f"{WORKDIR}/submission/tb.sv"
RUN_SH = "run.sh"   # bash harness: the agent's coverage report, workspace-relative
TOOLS = ".tools"    # bash harness: grader bundle that run.sh calls
SUBMISSION_DIR = f"{WORKDIR}/submission"  # campaign: up to max_files tb_*.sv files

_SUBMIT_RULE = {
    "null": "Reply with exactly one ```systemverilog code block containing the complete testbench.",
    "bash": f"Write the complete testbench to {SUBMISSION}; that file is what is graded.",
}

_CAMPAIGN_SUBMIT_RULE = {  # .format(max_files=...)
    "null": ("Reply with up to {max_files} ```systemverilog code blocks, each a "
             "complete testbench; every block is graded as a separate file."),
    "bash": (f"Write up to {{max_files}} testbenches as {SUBMISSION_DIR}/tb_<name>.sv "
             f"(<name>: letters, digits, _; at most {campaign.MAX_FILE_BYTES} bytes each); "
             "the first {max_files} non-empty ones by name are what is graded."),
}

_TASK = {
    False: """\
You are given an open-source design, its existing regression testbenches, the
functional coverage model, and a coverage report entry that has 0 hits. Write a
new SystemVerilog testbench that drives the design so the target coverage point
is hit.""",
    True: """\
You are given an open-source design, its existing regression testbenches, the
functional coverage model, and the coverage report entries of one module that
have 0 hits. Write up to {max_files} new SystemVerilog testbenches that
together hit as many of the target coverage points as possible.""",
}

_SYSTEM_TEMPLATE = """\
You are a hardware verification engineer doing coverage closure.

{task}

Rules:
- {submit}
- The top-level module must be named `tb`{each}.
- The testbench must end the simulation with $finish. A run that times out, stops
  without $finish, or ends with $fatal/$stop {fails}.
- Do not modify the design or the coverage model; only your testbench is used.
- Drive the design only through its ports, and instantiate it with its default
  parameters. A testbench that uses force/release, writes to signals inside the
  design, uses bind, redefines a design or coverage module, overrides a design
  parameter (#() or defparam), or calls $system, $c or file I/O is rejected
  before simulation and {fails}. Reading signals inside the design is allowed.
"""


def system_prompt(harness: str, max_files: int | None = None) -> str:
    """max_files: the campaign file cap; None for a single-target task."""
    c = max_files is not None
    rule = (_CAMPAIGN_SUBMIT_RULE if c else _SUBMIT_RULE)[harness]
    return _SYSTEM_TEMPLATE.format(
        task=_TASK[c].format(max_files=max_files), submit=rule.format(max_files=max_files),
        each=" in every testbench" if c else "", fails="contributes nothing" if c else "scores 0")


def _cover_location(design: Design, item: PlanItem) -> str:
    for f in design.covers:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if re.match(rf"\s*{re.escape(item.cover)}\s*:", line):
                return f"covers/{f.name}:{n}"
    raise ValueError(f"cover {item.cover} not found")


def module_of(design: Design, item: PlanItem) -> str:
    """The design module the item's cover is bound into (its bind statement)."""
    text = (design.pack / "covers" / f"{item.id}.sv").read_text()
    m = re.search(rf"^\s*bind\s+(\w+)\s+{re.escape(item.cover_module)}\b", text, re.M)
    if m is None:
        raise ValueError(f"{item.id}: no bind of {item.cover_module} in its cover file")
    return m.group(1)


def _entry(design: Design, item: PlanItem) -> str:
    return (f"```\npoint:  {item.cover}  (cover property in module {item.cover_module})\n"
            f"source: {_cover_location(design, item)}\nhits:   0\n```\n")


def visible_files(design: Design) -> dict[str, str]:
    """Agent-visible repo: workspace-relative path -> contents."""
    files = {f"rtl/{p.name}": p.read_text() for p in design.rtl}
    files.update({f"baseline/{b['file'].name}": b["file"].read_text()
                  for b in design.baselines.values()})
    files.update({f"covers/{p.name}": p.read_text() for p in design.covers})
    return files


def render(design: Design, item: PlanItem, run_timeout: float,
           harness: str = "null", agent_timeout: float | None = None,
           max_turns: int | None = None) -> str:
    flags = " ".join(VERILATOR_FLAGS)
    sections = [
        f"## Target: {item.id}\n\n{item.description}\n",
        "## Coverage report entry (baseline regression)\n\n" + _entry(design, item),
        "## How your testbench is run\n\n"
        "Compiled together with every file under rtl/ and covers/ using Verilator 5.020:\n"
        f"`verilator {flags} --top-module tb ...`\n"
        f"Simulation wall-clock limit: {int(run_timeout)} s. "
        "Reward is 1 only if the run reaches $finish cleanly and the target point is hit.\n",
    ]
    return _finish(design, sections, harness, agent_timeout, max_turns)


def render_campaign(design: Design, module: str, items: list[PlanItem], run_timeout: float,
                    max_files: int, harness: str = "null", agent_timeout: float | None = None,
                    max_turns: int | None = None) -> str:
    """A campaign: every target of one module, several testbenches, fractional reward."""
    flags = " ".join(VERILATOR_FLAGS)
    n = len(items)
    sections = [f"## Targets: module {module} ({n} coverage points with 0 hits)\n"]
    for item in items:
        sections += [f"### {item.id}\n\n{item.description}\n",
                     "Coverage report entry (baseline regression):\n\n" + _entry(design, item)]
    sections.append(
        "## How your testbenches are run\n\n"
        "Each testbench is compiled and simulated separately, together with every file "
        f"under rtl/ and covers/, using Verilator 5.020:\n`verilator {flags} --top-module tb ...`\n"
        f"Simulation wall-clock limit: {int(run_timeout)} s per testbench. "
        f"Reward = (targets hit by at least one testbench whose run reaches $finish cleanly) / {n}. "
        f"At most {max_files} testbenches are graded.\n")
    return _finish(design, sections, harness, agent_timeout, max_turns, max_files)


def _finish(design: Design, sections: list[str], harness: str, agent_timeout: float | None,
            max_turns: int | None, max_files: int | None = None) -> str:
    if harness == "bash":
        sections.append(_workspace(design, agent_timeout, max_turns, max_files))
        return "\n".join(sections)
    sections.append("## Repository")
    for path, text in visible_files(design).items():
        lang = "verilog" if path.endswith(".v") else "systemverilog"
        sections.append(f"### {path}\n\n```{lang}\n{text.rstrip()}\n```\n")
    return "\n".join(sections)


def _workspace(design: Design, agent_timeout: float | None, max_turns: int | None,
               max_files: int | None = None) -> str:
    files = "".join(f"- {p}\n" for p in visible_files(design))
    if max_files is not None:
        tools = (
            f"- {RUN_SH}: `./{RUN_SH} <file>...` compiles and simulates each file exactly as "
            "described above, with our cover files, and prints each file's run status, "
            "every target's hits across the files and what they would score together.\n"
            f"- submission/: empty. Write your final testbenches here as tb_<name>.sv; only "
            f"the first {max_files} non-empty ones by name are graded, in a fresh sandbox.\n")
        graded = "Whatever submission/ holds"
    else:
        tools = (
            f"- {RUN_SH}: `./{RUN_SH} <file>` compiles and simulates <file> exactly as described "
            "above, with our cover files, and prints the run status, the target's hits and "
            "whether it would score.\n"
            "- submission/tb.sv: empty. Write your final testbench here; only this file is "
            "graded, in a fresh sandbox.\n")
        graded = "Whatever submission/tb.sv holds"
    text = (f"## Workspace\n\nYour files are in {WORKDIR}:\n\n{files}{tools}"
            f"- {TOOLS}/: the grader that {RUN_SH} calls.\n")
    limits = [f"{int(agent_timeout)} s" if agent_timeout is not None else "",
              f"{max_turns} model turns (one reply with its tool calls is one turn)"
              if max_turns is not None else ""]
    if any(limits):
        text += (f"\nYour session is limited to {' and '.join(l for l in limits if l)}. "
                 f"{graded} when you stop or a limit is reached is graded.\n")
    return text


CODE_BLOCK = re.compile(r"```(?:systemverilog|verilog|sv)?[ \t]*\n(.*?)```", re.S)


def extract_testbench(reply: str | None) -> str:
    """The last fenced code block in the reply; empty if there is none."""
    blocks = CODE_BLOCK.findall(reply or "")
    return blocks[-1].strip() + "\n" if blocks else ""


def extract_testbenches(reply: str | None, max_files: int) -> dict[str, str]:
    """Campaign, null harness: the first max_files non-empty code blocks as tb_<n>.sv."""
    blocks = [b.strip() + "\n" for b in CODE_BLOCK.findall(reply or "") if b.strip()]
    return {f"tb_{i}.sv": b for i, b in enumerate(blocks[:max_files], 1)}


def grader_bundle(design: Design) -> dict[str, bytes]:
    """Files the grading sandbox needs, keyed by path relative to the bundle root.

    Mirrors the repo layout so closure_core.design.load_design works unchanged.
    Every pack-level YAML is shipped (design, plan, waivers, sources), so a new
    file referenced from design.yaml cannot silently break grading;
    tests/test_bundle.py checks that the bundle loads on its own. Golds and
    near-misses stay out.
    """
    root = design.repo_root
    core = root / "closure_core"
    paths: list[Path] = [*core.glob("*.py"), core / "sim_main.cpp",
                         *sorted(design.pack.glob("*.yaml")),
                         *design.rtl, *design.covers,
                         *(b["file"] for b in design.baselines.values()),
                         *(b["file"] for b in design.randoms.values())]  # load_design resolves them
    bundle = {str(p.relative_to(root)): p.read_bytes() for p in paths}
    bundle["campaign.py"] = Path(campaign.__file__).read_bytes()  # campaign scoring, stdlib only
    return bundle


def workspace_tools(design: Design, targets: list[str], run_timeout: float,
                    max_files: int | None = None) -> dict[str, bytes]:
    """Bash harness: run.sh plus what it needs, keyed by workspace-relative path.

    run.sh runs the same grader CLI as the grading sandbox on the same bundle
    (so no golds or near-misses) and prints run_summary.py's short report. It
    is the reward function, by design; the grading sandbox still grades
    independently from its own copy.
    """
    files = {f"{TOOLS}/{rel}": data for rel, data in grader_bundle(design).items()}
    files[f"{TOOLS}/run_summary.py"] = Path(__file__).with_name("run_summary.py").read_bytes()
    target_args = " ".join(f"--target {shlex.quote(t)}" for t in targets)
    if max_files is not None:  # campaign
        files[RUN_SH] = f"""\
#!/bin/sh
# ./{RUN_SH} <testbench.sv>...: grade each as the grading sandbox will and print
# per-file statuses and per-target hits across the files.
[ $# -ge 1 ] || {{ echo "usage: ./{RUN_SH} <testbench.sv>..." >&2; exit 2; }}
exec python3 "$(dirname "$(realpath "$0")")/{TOOLS}/campaign.py" --summary \\
     --design {shlex.quote(design.name)} {target_args} --run-timeout {run_timeout} \\
     --max-files {max_files} -- "$@"
""".encode()
        return files
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
