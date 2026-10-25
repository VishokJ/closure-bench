"""Design packs: everything design-specific, described by designs/<name>/design.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PlanItem:
    id: str              # plan ID, e.g. "R1"
    cover: str           # cover label in the bind file, e.g. "R1_frame_error"
    cover_module: str    # module holding the cover, e.g. "cov_R1"
    description: str     # one line, shown to the agent
    tier: str            # predicted tier until calibration replaces it
    sources: tuple[dict, ...] = field(default_factory=tuple)  # role: evidence (default) | requirement
    provenance: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Design:
    name: str
    repo_root: Path
    rtl: tuple[Path, ...]       # pinned design files, absolute
    covers: tuple[Path, ...]    # our bind files, absolute: covers/<ID>.sv per plan item
    plan: tuple[PlanItem, ...]
    baselines: dict[str, dict]  # name -> {"top": ..., "file": absolute Path}
    pack: Path                  # designs/<name>/
    mutate: dict[Path, tuple[int, int]] = field(default_factory=dict)  # RTL file -> line range
    waivers: dict = field(default_factory=dict)  # waivers.yaml contents

    def item(self, plan_id: str) -> PlanItem:
        for it in self.plan:
            if it.id == plan_id:
                return it
        raise KeyError(f"no plan item {plan_id!r} in design {self.name!r}")


def find_repo_root(start: Path | None = None) -> Path:
    p = (start or Path(__file__)).resolve()
    for parent in [p, *p.parents]:
        if (parent / "designs").is_dir() and (parent / "closure_core").is_dir():
            return parent
    raise FileNotFoundError("closure-bench repo root not found")


def load_design(name_or_path: str | Path, repo_root: Path | None = None) -> Design:
    root = repo_root or find_repo_root()
    path = Path(name_or_path)
    pack = path if path.is_dir() else root / "designs" / str(name_or_path)
    spec = yaml.safe_load((pack / "design.yaml").read_text())
    plan_spec = yaml.safe_load((pack / spec["plan"]).read_text())

    def resolve(rel: str) -> Path:
        p = (root / rel).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"{rel} listed in {pack}/design.yaml does not exist")
        return p

    def cover_file(it: PlanItem) -> Path:
        p = (pack / "covers" / f"{it.id}.sv").resolve()
        if not p.is_file():
            raise FileNotFoundError(f"{it.id}: cover file {p} does not exist")
        return p

    plan = tuple(
        PlanItem(
            id=it["id"],
            cover=it["cover"],
            cover_module=it["cover_module"],
            description=it["description"],
            tier=it["tier"],
            sources=tuple(it.get("sources", [])),
            provenance=dict(it.get("provenance", {})),
        )
        for it in plan_spec["items"]
    )
    for it in plan:
        for s in it.sources:
            if s.get("role", "evidence") not in ("evidence", "requirement"):
                raise ValueError(f"{it.id}: unknown source role {s['role']!r}")
    ids = [it.id for it in plan]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate plan IDs in {pack}")

    return Design(
        name=spec["name"],
        repo_root=root,
        pack=pack.resolve(),
        rtl=tuple(resolve(r) for r in spec["rtl"]),
        covers=tuple(cover_file(it) for it in plan),
        plan=plan,
        baselines={
            k: {"top": v["top"], "file": resolve(v["file"])}
            for k, v in spec.get("baselines", {}).items()
        },
        mutate={resolve(f): (lo, hi) for f, (lo, hi) in spec.get("mutate", {}).items()},
        waivers=(yaml.safe_load((pack / spec["waivers"]).read_text()) or {}) if "waivers" in spec else {},
    )
