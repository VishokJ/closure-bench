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
    near_miss_waiver: str | None = None  # why no near-miss is meaningful; audited
    composed_from: tuple[str, ...] = ()  # plan IDs a composed item is built from (tools/compose)
    template: str | None = None          # its composition template: seq, count, cross, excl, budget


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
    golds: dict[str, Path] = field(default_factory=dict)  # plan ID -> gold/<ID>.sv, if present
    near_misses: dict[str, tuple[Path, ...]] = field(default_factory=dict)  # near_miss/<ID>_*.sv
    randoms: dict[str, dict] = field(default_factory=dict)  # fixed-seed random TBs, like baselines
    multi: dict[str, tuple[str, ...]] = field(default_factory=dict)  # multi-target task ID -> plan IDs

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
            near_miss_waiver=(str(it["near_miss_waiver"]).strip() or None) if it.get("near_miss_waiver") else None,
            composed_from=tuple(map(str, it.get("composed_from") or ())),
            template=it.get("template"),
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
    for it in plan:
        if set(it.composed_from) - set(ids) or it.id in it.composed_from:
            raise ValueError(f"{it.id}: composed_from must name other plan items, got {list(it.composed_from)}")
    multi = {m["id"]: tuple(m["targets"])
             for m in (yaml.safe_load((pack / spec["multi"]).read_text()) or {}).get("multi", [])} \
        if "multi" in spec else {}
    for mid, ts in multi.items():
        if mid in ids or len(ts) < 2 or set(ts) - set(ids):
            raise ValueError(f"multi-target {mid}: needs a new ID and >= 2 existing plan IDs, got {list(ts)}")

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
        randoms={k: {"top": v["top"], "file": resolve(v["file"])} for k, v in spec.get("random", {}).items()},
        multi=multi,
        mutate={resolve(f): (lo, hi) for f, (lo, hi) in spec.get("mutate", {}).items()},
        waivers=(yaml.safe_load((pack / spec["waivers"]).read_text()) or {}) if "waivers" in spec else {},
        golds={it.id: g.resolve() for it in plan if (g := pack / "gold" / f"{it.id}.sv").is_file()},
        near_misses={it.id: tuple(p.resolve() for p in sorted((pack / "near_miss").glob(f"{it.id}_*.sv")))
                     for it in plan},
    )
