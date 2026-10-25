"""What the agent sees: the repo an engineer would have, plus the coverage report
entry for the target and its one-line description.

Toolchain facts are stated (simulator, version, flags); solution hints are not.
"""

from __future__ import annotations

import re
from pathlib import Path

from closure_core.design import Design, PlanItem
from closure_core.sim import VERILATOR_FLAGS

SYSTEM_PROMPT = """\
You are a hardware verification engineer doing coverage closure.

You are given an open-source design, its existing regression testbenches, the
functional coverage model, and a coverage report entry that has 0 hits. Write a
new SystemVerilog testbench that drives the design so the target coverage point
is hit.

Rules:
- Reply with exactly one ```systemverilog code block containing the complete testbench.
- The top-level module must be named `tb`.
- The testbench must end the simulation with $finish. A run that times out, stops
  without $finish, or ends with $fatal/$stop scores 0.
- Do not modify the design or the coverage model; only your testbench is used.
- Drive the design only through its ports. A testbench that uses force/release,
  writes to signals inside the design, uses bind, redefines a design or coverage
  module, or calls $system, $c or file I/O is rejected before simulation and
  scores 0. Reading signals inside the design is allowed.
"""


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


def render(design: Design, item: PlanItem, run_timeout: float) -> str:
    flags = " ".join(VERILATOR_FLAGS)
    sections = [
        f"## Target: {item.id}\n\n{item.description}\n",
        "## Coverage report entry (baseline regression)\n\n"
        f"```\npoint:  {item.cover}  (cover property in module {item.cover_module})\n"
        f"source: {_cover_location(design, item)}\nhits:   0\n```\n",
        "## How your testbench is run\n\n"
        "Compiled together with every file under rtl/ and covers/ using Verilator 5.020:\n"
        f"`verilator {flags} --top-module tb ...`\n"
        f"Simulation wall-clock limit: {int(run_timeout)} s. "
        "Reward is 1 only if the run reaches $finish cleanly and the target point is hit.\n",
        "## Repository",
    ]
    for path, text in visible_files(design).items():
        lang = "verilog" if path.endswith(".v") else "systemverilog"
        sections.append(f"### {path}\n\n```{lang}\n{text.rstrip()}\n```\n")
    return "\n".join(sections)


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
    near-misses stay out.
    """
    root = design.repo_root
    core = root / "closure_core"
    paths: list[Path] = [*core.glob("*.py"), core / "sim_main.cpp",
                         *sorted(design.pack.glob("*.yaml")),
                         *design.rtl, *design.covers,
                         *(b["file"] for b in design.baselines.values()),
                         *(b["file"] for b in design.randoms.values())]  # load_design resolves them
    return {str(p.relative_to(root)): p.read_bytes() for p in paths}
