"""Parse Verilator coverage.dat and map functional cover points to plan IDs.

Provenance: a functional point counts only if
  - it comes from one of our cover files, in the module and under the label
    the plan names (a testbench's own cover with the same label does not count), and
  - it sits where our `bind` statement put it: instance name from the bind,
    directly under a real instance of the bound design module. A testbench that
    instantiates our cover module itself and drives its inputs does not count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from closure_core.design import Design

BIND_RE = re.compile(r"^\s*bind\s+(\w+)\s+(\w+)\s+(\w+)\s*\(", re.M)


@dataclass(frozen=True)
class CoverPoint:
    kind: str       # v_line | v_branch | v_toggle | v_user
    module: str     # module the point belongs to
    file: str
    line: int
    name: str       # label for v_user; signal/branch text otherwise
    hier: str       # full instance path
    hits: int


def parse(path: Path) -> list[CoverPoint]:
    points = []
    for raw in path.read_text(errors="replace").splitlines():
        if not raw.startswith("C '"):
            continue
        body, count = raw.rsplit(" ", 1)
        fields = {}
        for kv in body[3:-1].split("\x01")[1:]:
            if "\x02" in kv:
                k, v = kv.split("\x02", 1)
                fields[k] = v
        page = fields.get("page", "")
        kind, _, module = page.partition("/")
        points.append(CoverPoint(
            kind=kind, module=module, file=fields.get("f", ""),
            line=int(fields.get("l", 0) or 0), name=fields.get("o", ""),
            hier=fields.get("h", ""), hits=int(count),
        ))
    return points


def bind_sites(cover_files: list[Path]) -> dict[str, tuple[str, str]]:
    """cover module -> (bound design module, instance name), from our bind statements."""
    sites: dict[str, tuple[str, str]] = {}
    for f in cover_files:
        for target, module, inst in BIND_RE.findall(f.read_text()):
            sites[module] = (target, inst)
    return sites


def plan_hits(points: list[CoverPoint], design: Design, cover_files: list[Path]) -> dict[str, int]:
    """Hits per plan ID, counting only points with trusted provenance and placement.

    cover_files are the paths our cover files had at compile time.
    Hits from several DUT instances are summed.
    """
    trusted = {str(p.resolve()) for p in cover_files}
    sites = bind_sites(cover_files)
    # Hierarchy paths of every instance of each design module, from its line points.
    scopes: dict[str, set[str]] = {}
    for p in points:
        if p.kind == "v_line":
            scopes.setdefault(p.module, set()).add(p.hier)

    hits = {it.id: 0 for it in design.plan}
    for it in design.plan:
        if it.cover_module not in sites:
            raise ValueError(f"{it.id}: no bind statement for cover module {it.cover_module}")
        target, inst = sites[it.cover_module]
        suffix = f".{inst}.{it.cover}"
        for p in points:
            if (p.kind == "v_user" and str(Path(p.file).resolve()) in trusted
                    and p.module == it.cover_module and p.name == it.cover
                    and p.hier.endswith(suffix)
                    and p.hier[: -len(suffix)] in scopes.get(target, set())):
                hits[it.id] += p.hits
    return hits
