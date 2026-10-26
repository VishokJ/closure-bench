"""Campaign scoring: several testbenches against every target of one module.

Each file is graded separately by the unchanged grader CLI (all-or-nothing per
file, on all the campaign's targets); this module only takes the union of
target hits over files whose status is ok:

    reward = targets hit by at least one ok file / number of targets

The grade records reward_kind "fraction" (the single-target grader's reward is
all-or-nothing). At most max_files files are graded: by default one per target.

A file that is not ok (policy_violation included) contributes nothing; its
status is recorded per file. Standard library only: it runs next to
closure_core in the grading sandbox (/grader/campaign.py) and in the agent's
sandbox (/workspace/.tools/campaign.py, behind run.sh).

CLI:
    python3 campaign.py --design uart --target R1 --target R2 [--max-files N] --dir submission/
    python3 campaign.py --design uart --target R1 --summary a.sv b.sv
--dir grades the files a submission keeps (what the grading sandbox does);
explicit files are graded as given (run.sh). Prints JSON, or with --summary the text
run.sh shows. Nonzero exit means grading itself failed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_FILE_BYTES = 1_000_000
NAME = re.compile(r"tb_[A-Za-z0-9_]+\.sv")
STATUSES = ("ok", "compile_error", "compile_timeout", "timeout", "runtime_error",
            "no_finish", "policy_violation")


def eligible(sizes: dict[str, int]) -> list[str]:
    """File name -> size in bytes: the candidate names, in grading order.

    A submission keeps the first max_files of these whose text is not blank
    (keep()), so empty files never take a slot.
    """
    return sorted(n for n, s in sizes.items() if NAME.fullmatch(n) and 0 < s <= MAX_FILE_BYTES)


def keep(texts: dict[str, str], max_files: int) -> dict[str, str]:
    """Name -> text, in eligible() order: the non-blank files a submission keeps."""
    return dict([(n, t) for n, t in texts.items() if t.strip()][:max_files])


def combine(targets: list[str], results: dict[str, dict]) -> dict:
    """Per-file grader results -> the campaign grade."""
    hits = {t: 0 for t in targets}
    for g in results.values():
        if g["status"] == "ok":
            for t in targets:
                hits[t] += g["target_hits"][t]
    hit = sum(h > 0 for h in hits.values())
    return {"targets": list(targets), "target_hits": hits, "targets_hit": hit,
            "reward": hit / len(targets), "reward_kind": "fraction", "files": results}


def grade_files(design: str, targets: list[str], run_timeout: float,
                files: dict[str, Path]) -> dict:
    """Grade each file (key: the name it is reported under) with the grader CLI."""
    target_args = [a for t in targets for a in ("--target", t)]
    results = {}
    for name, path in files.items():
        res = subprocess.run(
            [sys.executable, "-m", "closure_core.grader", "--design", design, *target_args,
             "--run-timeout", str(run_timeout), str(path)],
            cwd=Path(__file__).resolve().parent, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"grader failed on {name} ({res.returncode}): {res.stderr[-2000:]}")
        results[name] = json.loads(res.stdout)
    return combine(targets, results)


def summary(c: dict) -> str:
    lines = []
    for name, g in c["files"].items():
        hit = [t for t, h in g["target_hits"].items() if h > 0]
        lines.append(f"file {name}: {g['status']}" + (f", hits {' '.join(hit)}" if hit else ""))
    lines += [f"target {t}: {h} hits" for t, h in c["target_hits"].items()]
    lines.append(f"would score: {c['targets_hit']}/{len(c['targets'])} = {c['reward']:.2f}")
    for name, g in c["files"].items():
        if g["status"] == "policy_violation":
            lines += ["", f"{name}: policy violations:", g["diagnostics"]]
        elif g["status"] != "ok":
            lines += ["", f"{name}: log tail:", g["diagnostics"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--design", required=True)
    ap.add_argument("--target", action="append", required=True)
    ap.add_argument("--run-timeout", type=float, default=60.0)
    ap.add_argument("--max-files", type=int, help="default: the number of targets")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--dir", type=Path)
    ap.add_argument("testbench", nargs="*", type=Path)
    args = ap.parse_args(argv)
    max_files = args.max_files or len(args.target)
    if args.dir is not None:
        regular = [p for p in args.dir.iterdir() if p.is_file() and not p.is_symlink()]
        names = eligible({p.name: p.stat().st_size for p in regular})
        texts = keep({n: (args.dir / n).read_text(errors="replace") for n in names}, max_files)
        files = {n: args.dir / n for n in texts}
    else:
        missing = [str(p) for p in args.testbench if not p.is_file()]
        if missing or not args.testbench:
            print(f"no such file: {' '.join(missing)}" if missing else "no testbench given",
                  file=sys.stderr)
            return 2
        files = {str(p): p.resolve() for p in args.testbench}
    c = grade_files(args.design, args.target, args.run_timeout, files)
    if args.summary:
        print(summary(c))
        if args.dir is None and (len(args.testbench) > max_files or eligible(
                {p.name: p.stat().st_size for p in args.testbench}) != sorted(p.name for p in args.testbench)):
            print(f"\nnote: only non-empty submission/tb_*.sv files are graded, at most "
                  f"{max_files} (first by name), {MAX_FILE_BYTES} bytes each")
    else:
        print(json.dumps(c, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
