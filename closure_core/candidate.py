"""Gate one candidate plan item on an overlay of a design pack.

The overlay is a temporary copy of the pack with the candidate added; the
real pack is never written. Gates run cheapest first and stop at the first
failure (the rest are recorded as skipped), so a broken candidate fails in
seconds and a repair turn gets feedback fast:

  format        the candidate directory is complete and consistently named
  cover_sync .. determinism, value, duplicate: closure_core/gates.py
                (formal runs only without gold.sv or with twin.sv; value needs
                the mutation runs, the expensive part; duplicate compares
                against every item already in the pack and needs their golds)

Candidate directory:
  item.yaml        one plan entry: id, cover, cover_module, description, tier, sources
                   (+ near_miss_waiver: a reason, only if there is no near-miss)
                   (+ composed_from: plan IDs whose verified requirements it inherits)
  cover.sv         module cov_<id> and its bind
  gold.sv          optional self-checking gold testbench (top `tb`): the checking gold.
                   Without it, a formal witness becomes the reach gold.
  twin.sv          optional cover cov_<id>_twin of the off-by-one condition; its
                   formal witness becomes the near-miss near_miss/<id>_twin.sv
  near_miss/*.sv   near-miss testbenches: at least one (a twin counts), unless near_miss_waiver
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import yaml

from closure_core import citations, gates
from closure_core.design import find_repo_root, load_design
from closure_core.gates import GateResult
from closure_core.grader import score
from closure_core.infra import simulate

ORDER = ["format", "cover_sync", "cover_policy", "description_sync", "mechanism", "citations", "formal", "baseline",
         "gold", "near_miss", "determinism", "value", "duplicate"]
REQUIRED = ("id", "cover", "cover_module", "description", "tier", "sources")
ID_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


def check_format(cand: Path, existing_ids: set[str]) -> GateResult:
    missing = [f for f in ("item.yaml", "cover.sv") if not (cand / f).is_file()]
    if missing:
        return GateResult("format", False, f"missing {', '.join(missing)}")
    try:
        item = yaml.safe_load((cand / "item.yaml").read_text())
    except yaml.YAMLError as e:
        return GateResult("format", False, f"item.yaml is not valid YAML: {e}")
    if not isinstance(item, dict):
        return GateResult("format", False, "item.yaml must be a mapping")
    errs = [f"item.yaml lacks {k!r}" for k in REQUIRED if k not in item]
    i = str(item.get("id", ""))
    if not ID_RE.match(i):
        errs.append(f"id {i!r} must match {ID_RE.pattern}")
    if i in existing_ids:
        errs.append(f"id {i!r} is already in the plan")
    if item.get("cover_module") != f"cov_{i}":
        errs.append(f"cover_module must be cov_{i}")
    if not str(item.get("cover", "")).startswith(f"{i}_"):
        errs.append(f"cover label must start with {i}_")
    if not isinstance(item.get("sources"), list) or not item.get("sources"):
        errs.append("sources must be a non-empty list")
    comp = item.get("composed_from")
    if comp is not None and (not isinstance(comp, list) or not set(map(str, comp)) <= existing_ids):
        errs.append(f"composed_from must list existing plan IDs, got {comp!r}")
    # The header marks a reach gold, which is exempt from the must-$fatal rule.
    if (cand / "gold.sv").is_file() and gates.gold_source(cand / "gold.sv") == "formal":
        errs.append(f"gold.sv may not start with {gates.REACH_HEADER!r} (reserved for formal witnesses)")
    if (cand / "twin.sv").is_file() and (cand / "near_miss" / "twin.sv").is_file():
        errs.append("near_miss/twin.sv clashes with the twin's witness; rename it")
    return GateResult("format", not errs, "; ".join(errs))


def overlay(base_pack: Path, cand: Path, dest: Path) -> str:
    """Copy base_pack to dest and add the candidate to it; returns the item ID."""
    shutil.copytree(base_pack, dest)
    return add(dest, cand)


def add(pack: Path, cand: Path, reach_gold: str | None = None, twin_near_miss: str | None = None) -> str:
    """Add a candidate to a pack in place (only ever an overlay or a run's own pack).

    reach_gold, twin_near_miss: the formal witnesses' testbenches (gates.reach_gold_text,
    gates.twin_near_miss_text), for a candidate without gold.sv or with twin.sv.
    """
    item = yaml.safe_load((cand / "item.yaml").read_text())
    i = item["id"]
    plan_path = pack / yaml.safe_load((pack / "design.yaml").read_text())["plan"]
    plan = yaml.safe_load(plan_path.read_text())
    plan["items"] = [*(plan.get("items") or []), item]
    plan_path.write_text(yaml.safe_dump(plan, sort_keys=False))
    shutil.copy(cand / "cover.sv", pack / "covers" / f"{i}.sv")
    (pack / "gold").mkdir(exist_ok=True)
    if (cand / "gold.sv").is_file():
        shutil.copy(cand / "gold.sv", pack / "gold" / f"{i}.sv")
    elif reach_gold is not None:
        (pack / "gold" / f"{i}.sv").write_text(reach_gold)
    (pack / "near_miss").mkdir(exist_ok=True)
    for p in sorted((cand / "near_miss").glob("*.sv")):
        shutil.copy(p, pack / "near_miss" / f"{i}_{p.name}")
    if twin_near_miss is not None:
        (pack / "near_miss" / f"{i}_twin.sv").write_text(twin_near_miss)
    return i


def gate(base_pack: Path, cand: Path, *, cache_path: Path, j: int = 4, offline: bool = False,
         witness_cache: Path | None = None, min_depth: int | None = None,
         require_mechanism: bool = False) -> dict:
    """Run the gates on one candidate; stops at the first failure.

    witness_cache: directory of formal witnesses by key (gates.witness); a run
    keeps its own, so a replay reuses every witness instead of re-solving.
    min_depth: reject reach witnesses shallower than this (hardening).
    require_mechanism: item.yaml must declare at least gates.MIN_MECHANISMS distinct
    difficulty mechanisms (target-only runs).
    Raises infra.InfraError (gates.FormalError is one) when the machine fails, e.g. a
    simulation times out twice: not a decision, nothing is recorded.
    """
    root = find_repo_root()
    base = load_design(base_pack, repo_root=root)
    results: list[GateResult] = []

    def ok(r: GateResult) -> bool:
        results.append(r)
        return r.ok in (True, "n/a")

    pack_dir = ""

    def finish(item_id: str | None) -> dict:
        failed = next((r.gate for r in results if r.ok not in (True, "n/a")), None)
        res = {"item": item_id, "accepted": failed is None, "failed_gate": failed,
               "gates": [asdict(r) for r in results], "skipped": ORDER[len(results):]}
        # The overlay is a temp dir: normalise it so results are comparable across runs.
        text = json.dumps(res, default=str)
        return json.loads(text.replace(pack_dir, "<pack>") if pack_dir else text)

    if not ok(check_format(cand, {it.id for it in base.plan})):
        return finish(None)
    with tempfile.TemporaryDirectory(prefix="cb-overlay-") as d, ThreadPoolExecutor(j) as pool:
        i = overlay(base.pack, cand, Path(d) / "pack")
        design = load_design(Path(d) / "pack", repo_root=root)
        pack_dir = str(design.pack)
        it = design.item(i)
        base_futs = {n: pool.submit(simulate, design, b["file"].read_text(), top=b["top"])
                     for n, b in design.baselines.items()}
        rand_futs = {n: pool.submit(simulate, design, b["file"].read_text(), top=b["top"])
                     for n, b in design.randoms.items()}

        if not ok(gates.cover_sync(it, gates.cover_labels(design))):
            return finish(i)
        parsed = gates.parse_cover(design, it)
        if not ok(gates.cover_policy(design, it, parsed)) or not ok(gates.description_sync(design, it, parsed)):
            return finish(i)
        raw = yaml.safe_load((cand / "item.yaml").read_text())
        if not ok(gates.mechanism(design, it, raw, (cand / "twin.sv").is_file(), parsed, require_mechanism)):
            return finish(i)
        baselines = {n: f.result() for n, f in base_futs.items()}
        cites = gates.citations(design, it, citations.DocStore(design.pack, offline=offline),
                                [p for s in baselines.values() for p in s.points])
        randoms = {n: f.result() for n, f in rand_futs.items()}
        if not ok(cites):
            return finish(i)

        has_gold, twin = (cand / "gold.sv").is_file(), cand / "twin.sv"
        twin = twin if twin.is_file() else None
        if has_gold and not twin:
            ok(gates.formal(it, None))  # n/a
        else:
            bound = gates.formal_settings(design)["bound"]
            # Named as the repo path the proposer sees, also when the base is a run's snapshot.
            kw = {"assumptions": f"designs/{base.name}/{gates.FORMAL_DIR}/", "bound": bound, "min_depth": min_depth}
            w = None if has_gold else gates.witness(design, design.pack / "covers" / f"{i}.sv", witness_cache)
            fr = gates.formal(it, w, **kw)
            tw = None
            if fr.ok in (True, "n/a") and twin:  # the twin only once the target is settled
                tv = gates.twin_policy(design, twin, i)
                tw = None if tv else gates.witness(design, twin, witness_cache)
                fr = gates.formal(it, w, tw, twin_violations=tv, **kw)
            if not ok(fr):
                return finish(i)
            # The witnesses join the overlay as the reach gold and a near-miss.
            if w:
                (design.pack / "gold" / f"{i}.sv").write_text(gates.reach_gold_text(w, bound))
            if tw:
                (design.pack / "near_miss" / f"{i}_twin.sv").write_text(gates.twin_near_miss_text(tw, bound))
            design = load_design(design.pack, repo_root=root)
            it = design.item(i)

        if not ok(gates.baseline(it, baselines, randoms)):
            return finish(i)

        gold_path = design.golds[i]
        gold_pol = pool.submit(gates.testbench_policy, design, gold_path, gold=True)
        sa, sb = (f.result() for f in [pool.submit(simulate, design, gold_path.read_text())
                                       for _ in range(2)])
        a, b = score(design, [i], sa), score(design, [i], sb)
        g = gates.gold(it, a, gold_pol.result())
        g.data["gold_source"] = gates.gold_source(gold_path)
        g.data["holes_hit"] = sorted(set(gates.holes(baselines)) & gates.hit_points(sa))
        if not ok(g):
            return finish(i)

        nms = design.near_misses.get(i, ())
        nm_pol = {p.name: pool.submit(gates.testbench_policy, design, p, gold=False) for p in nms}
        nm = [(p.name, f.result()) for p, f in [(p, pool.submit(simulate, design, p.read_text()))
                                                for p in nms]]
        # A composed item's components' testbenches: already gated, so no policy check here.
        inh = {n: pool.submit(simulate, design, p.read_text()) for n, p in gates.composed_testbenches(design, it).items()}
        inh_nm = gates.composed_near_misses(it, {n: f.result() for n, f in inh.items()})
        if not ok(gates.near_miss(it, [(n, score(design, [i], s)) for n, s in nm + inh_nm],
                                  {n: f.result() for n, f in nm_pol.items()},
                                  {n: gates.line_overlap(sa, s) for n, s in nm + inh_nm})):
            return finish(i)
        if not ok(gates.determinism(a, b)):
            return finish(i)

        # Every gold, not only the candidate's: only_gold_kills and same-kill reports
        # then compare against the existing items too (cached after the first run).
        mutation = gates.mutation_runs(design, design.golds, pool, cache_path)
        inherited = gates.inherited_requirements(design, it, citations.DocStore(design.pack, offline=offline),
                                                 [p for s in baselines.values() for p in s.points])
        if not ok(gates.value(mutation["gold_kills"].get(i, []), mutation["only_gold_kills"].get(i, []),
                              cites.data["verified"], inherited)):
            return finish(i)

        # Duplicate: every testbench of every item, so each pair can find a witness.
        others = [(f"gold:{x}", p) for x, p in design.golds.items() if x != i]
        others += [(f"near_miss:{p.name}", p) for x, ps in design.near_misses.items() if x != i for p in ps]
        other_sims = {k: pool.submit(simulate, design, p.read_text()) for k, p in others}
        corpus = {f"baseline:{n}": s.plan_hits for n, s in baselines.items() if s.sim.status == "ok"}
        corpus.update({f"random:{n}": s.plan_hits for n, s in randoms.items() if s.sim.status == "ok"})
        corpus[f"gold:{i}"] = sa.plan_hits
        corpus.update({f"near_miss:{n}": s.plan_hits for n, s in nm if s.sim.status == "ok"})
        corpus.update({k: s.plan_hits for k, f in other_sims.items() if (s := f.result()).sim.status == "ok"})
        dups, _ = gates.duplicate(corpus, [x.id for x in design.plan], mutation["gold_kills"])
        ok(dups[i])
        return finish(i)
