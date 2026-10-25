"""Bash harness: what `./run.sh <tb.sv>` prints in the agent sandbox.

Installed as /workspace/.tools/run_summary.py; run.sh pipes the grader CLI's
JSON into it. Standard library only: the agent sandbox has no closure_bench.
"""

from __future__ import annotations

import json
import sys


def summary(g: dict) -> str:
    lines = [f"status: {g['status']}"]
    lines += [f"target {t}: {h} hits" for t, h in g["target_hits"].items()]
    lines.append(f"would score: {int(g['reward'])}")
    if g["status"] == "policy_violation":
        lines += ["", "policy violations:", g["diagnostics"]]
    elif g["status"] != "ok":
        lines += ["", "log tail:", g["diagnostics"]]
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary(json.load(sys.stdin)))
