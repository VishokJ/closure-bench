"""Gate one candidate plan item on an overlay of a design pack.

The overlay is a temporary copy of the pack with the candidate added; the
real pack is never written. Gates run cheapest first and stop at the first
failure (the rest are recorded as skipped), so a broken candidate fails in
seconds and a repair turn gets feedback fast:

  format        the candidate directory is complete and consistently named
  cover_sync .. determinism, value, duplicate: closure_core/gates.py
                (value needs the mutation runs, the expensive part; duplicate
                compares against every item already in the pack and needs
                their golds)

Candidate directory:
  item.yaml        one plan entry: id, cover, cover_module, description, tier, sources
  cover.sv         module cov_<id> and its bind
  gold.sv          self-checking gold testbench (top `tb`)
  near_miss/*.sv   optional near-miss testbenches
"""

from __future__ import annotations

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
from closure_core.grader import score, simulate

ORDER = ["format", "cover_sync", "cover_policy", "citations", "baseline", "gold", "near_miss",
         "determinism", "value", "duplicate"]
REQUIRED = ("id", "cover", "cover_module", "description", "tier", "sources")
ID_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")


def check_format(cand: Path, existing_ids: set[str]) -> GateResult:
    missing = [f for f in ("item.yaml", "cover.sv", "gold.sv") if not (cand / f).is_file()]
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
    return GateResult("format", not errs, "; ".join(errs))


def overlay(base_pack: Path, cand: Path, dest: Path) -> str:
    """Copy base_pack to dest and add the candidate to it; returns the item ID."""
    shutil.copytree(base_pack, dest)
    item = yaml.safe_load((cand / "item.yaml").read_text())
    i = item["id"]
    plan_path = dest / yaml.safe_load((dest / "design.yaml").read_text())["plan"]
    plan = yaml.safe_load(plan_path.read_text())
    plan["items"] = [*(plan.get("items") or []), item]
    plan_path.write_text(yaml.safe_dump(plan, sort_keys=False))
    shutil.copy(cand / "cover.sv", dest / "covers" / f"{i}.sv")
    (dest / "gold").mkdir(exist_ok=True)
    shutil.copy(cand / "gold.sv", dest / "gold" / f"{i}.sv")
    (dest / "near_miss").mkdir(exist_ok=True)
    for p in sorted((cand / "near_miss").glob("*.sv")):
        shutil.copy(p, dest / "near_miss" / f"{i}_{p.name}")
    return i


def gate(base_pack: Path, cand: Path, *, cache_path: Path, j: int = 4, offline: bool = False) -> dict:
    """Run the gates on one candidate; stops at the first failure."""
    root = find_repo_root()
    base = load_design(base_pack, repo_root=root)
    results: list[GateResult] = []

    def ok(r: GateResult) -> bool:
        results.append(r)
        return r.ok in (True, "n/a")

    def finish(item_id: str | None) -> dict:
        failed = next((r.gate for r in results if r.ok not in (True, "n/a")), None)
        return {"item": item_id, "accepted": failed is None, "failed_gate": failed,
                "gates": [asdict(r) for r in results], "skipped": ORDER[len(results):]}

    if not ok(check_format(cand, {it.id for it in base.plan})):
        return finish(None)
    with tempfile.TemporaryDirectory(prefix="cb-overlay-") as d, ThreadPoolExecutor(j) as pool:
        i = overlay(base.pack, cand, Path(d) / "pack")
        design = load_design(Path(d) / "pack", repo_root=root)
        it = design.item(i)
        base_futs = {n: pool.submit(simulate, design, b["file"].read_text(), top=b["top"])
                     for n, b in design.baselines.items()}

        if not ok(gates.cover_sync(it, gates.cover_labels(design))):
            return finish(i)
        if not ok(gates.cover_policy(design, it)):
            return finish(i)
        baselines = {n: f.result() for n, f in base_futs.items()}
        cites = gates.citations(design, it, citations.DocStore(design.pack, offline=offline),
                                [p for s in baselines.values() for p in s.points])
        if not ok(cites) or not ok(gates.baseline(it, baselines)):
            return finish(i)

        gold_path = design.golds[i]
        gold_pol = pool.submit(gates.testbench_policy, design, gold_path, gold=True)
        sa, sb = (f.result() for f in [pool.submit(simulate, design, gold_path.read_text())
                                       for _ in range(2)])
        a, b = score(design, [i], sa), score(design, [i], sb)
        if not ok(gates.gold(it, a, gold_pol.result())):
            return finish(i)

        nms = design.near_misses.get(i, ())
        nm_pol = {p.name: pool.submit(gates.testbench_policy, design, p, gold=False) for p in nms}
        nm = [(p.name, f.result()) for p, f in [(p, pool.submit(simulate, design, p.read_text()))
                                                for p in nms]]
        if not ok(gates.near_miss(it, [(n, score(design, [i], s)) for n, s in nm],
                                  {n: f.result() for n, f in nm_pol.items()},
                                  {n: gates.line_overlap(sa, s) for n, s in nm})):
            return finish(i)
        if not ok(gates.determinism(a, b)):
            return finish(i)

        mutation = gates.mutation_runs(design, {i: gold_path}, pool, cache_path)
        if not ok(gates.value(mutation["gold_kills"].get(i, []), mutation["only_gold_kills"].get(i, []),
                              cites.data["verified"])):
            return finish(i)

        # Duplicate: every testbench of every item, so each pair can find a witness.
        others = [(f"gold:{x}", p) for x, p in design.golds.items() if x != i]
        others += [(f"near_miss:{p.name}", p) for x, ps in design.near_misses.items() if x != i for p in ps]
        other_sims = {k: pool.submit(simulate, design, p.read_text()) for k, p in others}
        corpus = {f"baseline:{n}": s.plan_hits for n, s in baselines.items() if s.sim.status == "ok"}
        corpus[f"gold:{i}"] = sa.plan_hits
        corpus.update({f"near_miss:{n}": s.plan_hits for n, s in nm if s.sim.status == "ok"})
        corpus.update({k: s.plan_hits for k, f in other_sims.items() if (s := f.result()).sim.status == "ok"})
        dups, _ = gates.duplicate(corpus, [x.id for x in design.plan], mutation["gold_kills"])
        ok(dups[i])
        return finish(i)
