"""grade(): the single function that decides a reward.

The submission is graded in a fresh directory containing only the pinned RTL,
our cover files, our simulation driver and the submitted testbench. Reward is
1.0 only if the simulation ran cleanly to $finish and every target was hit.

CLI (used inside the grading sandbox):
    python -m closure_core.grader --design uart --target R1 path/to/tb.sv
prints a GradeResult as JSON on stdout and exits 0 whenever a grade was
computed, including reward 0. Nonzero exit means grading itself failed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from closure_core import coverage, sim
from closure_core.design import Design, load_design

SUBMISSION_TOP = "tb"  # agent testbenches must name their top module `tb`


@dataclass
class GradeResult:
    design: str
    targets: list[str]
    status: str                    # sim status, see closure_core.sim
    reward: float
    target_hits: dict[str, int]
    plan_hits: dict[str, int]      # every plan item, for metrics and analysis
    compile_s: float
    run_s: float
    diagnostics: str               # log tail when not ok, else empty
    toolchain: str = ""
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


@dataclass
class Simulation:
    sim: sim.SimResult
    points: list[coverage.CoverPoint]   # every coverage point; empty unless status ok
    plan_hits: dict[str, int]           # trusted hits per plan ID


def simulate(
    design: Design,
    tb_text: str,
    *,
    top: str = SUBMISSION_TOP,
    compile_timeout: float = 120.0,
    run_timeout: float = 60.0,
    keep_workdir: Path | None = None,
) -> Simulation:
    """Run one testbench against the pinned RTL and our covers in a fresh directory."""
    work = Path(tempfile.mkdtemp(prefix="cb-sim-"))
    try:
        (work / "rtl").mkdir()
        (work / "covers").mkdir()
        (work / "submission").mkdir()
        rtl = [Path(shutil.copy2(f, work / "rtl" / f.name)) for f in design.rtl]
        covers = [Path(shutil.copy2(f, work / "covers" / f.name)) for f in design.covers]
        tb = work / "submission" / "tb.sv"
        tb.write_text(tb_text)

        res = sim.build_and_run(work, [*rtl, *covers, tb], top,
                                compile_timeout=compile_timeout, run_timeout=run_timeout)
        points: list[coverage.CoverPoint] = []
        hits = {it.id: 0 for it in design.plan}
        if res.status == "ok":
            points = coverage.parse(res.coverage_file)
            hits = coverage.plan_hits(points, design, covers)
        # Logs mention the temp dir; normalise so results are comparable across runs.
        res = sim.SimResult(res.status, None, res.compile_log.replace(str(work), "<work>"),
                            res.run_log.replace(str(work), "<work>"),
                            res.compile_s, res.run_s, res.exit_code)
        points = [coverage.CoverPoint(p.kind, p.module, p.file.replace(str(work), "<work>"),
                                      p.line, p.name, p.hier, p.hits) for p in points]
        return Simulation(res, points, hits)
    finally:
        if keep_workdir:
            shutil.copytree(work, keep_workdir, dirs_exist_ok=True)
        shutil.rmtree(work, ignore_errors=True)


def grade(
    design: Design,
    targets: list[str],
    tb_text: str,
    *,
    top: str = SUBMISSION_TOP,
    compile_timeout: float = 120.0,
    run_timeout: float = 60.0,
    keep_workdir: Path | None = None,
) -> GradeResult:
    for t in targets:
        design.item(t)  # unknown target is a grader bug: raise, don't score 0

    s = simulate(design, tb_text, top=top, compile_timeout=compile_timeout,
                 run_timeout=run_timeout, keep_workdir=keep_workdir)
    return score(design, targets, s)


def score(design: Design, targets: list[str], s: Simulation) -> GradeResult:
    """The reward for one simulation; grade() is simulate() followed by this."""
    target_hits = {t: s.plan_hits[t] for t in targets}
    ok = s.sim.status == "ok"
    reward = float(ok and all(h > 0 for h in target_hits.values()))
    return GradeResult(
        design=design.name, targets=list(targets), status=s.sim.status,
        reward=reward, target_hits=target_hits, plan_hits=s.plan_hits,
        compile_s=round(s.sim.compile_s, 2), run_s=round(s.sim.run_s, 2),
        diagnostics="" if ok else (s.sim.run_log or s.sim.compile_log),
        toolchain=sim.verilator_version(),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--design", required=True)
    ap.add_argument("--target", action="append", required=True)
    ap.add_argument("--top", default=SUBMISSION_TOP)
    ap.add_argument("--run-timeout", type=float, default=60.0)
    ap.add_argument("testbench", type=Path)
    args = ap.parse_args(argv)
    design = load_design(args.design)
    res = grade(design, args.target, args.testbench.read_text(),
                top=args.top, run_timeout=args.run_timeout)
    print(res.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
