"""Gates: the mechanical checks a plan item must pass before it can be a task.

Each gate is a function of simulation results (from grader.grade/simulate)
that returns a GateResult. Running the simulations is left to the caller, so
tools/check can run everything in parallel while tools/gate_candidate runs
gates one at a time, cheapest first, stopping at the first failure.

  citations     every cited source verifies (RTL/README anchors, DOC page+hash, BASE point)
  cover_sync    exactly one cover with the item's label, in the module the plan names
  baseline      no baseline testbench hits the item (the task is not free)
  gold          the gold testbench scores 1 (the task is solvable)
  near_miss     every near-miss testbench scores 0 (boundary is exact)
  determinism   grading the gold twice gives an identical result
  value         evidence the item matters, either kind is enough:
                mutant: the gold kills at least one mutant every baseline
                  survives (closure_core/mutants.py; a kill = passes on the
                  original RTL, fails on the mutant);
                spec: a verified DOC or README source with role: requirement.
                Mutants are one-line edits and cannot represent missing
                features or spec mismatches, so no kill is only absence of
                evidence. Kills are computed for every item either way.
                Spec-only items are always in the audit sample.
  duplicate     some testbench we run (baseline, gold, near-miss) hits this item
                and not the other, for every other item compared. A signature
                is the set of testbenches that hit an item; adding testbenches
                can only split signatures, never merge them. Reported, not
                enforced: implications (this gold also hits item X) and items
                whose golds kill the same baseline-surviving mutants.

No gate calls a model. Solvability from the agent's view is established by the
pilot; items no pilot model solves get a fairness check (docs/PLAN.md §6).
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from pathlib import Path

from closure_core import citations as cit
from closure_core import mutants
from closure_core.design import Design, PlanItem
from closure_core.grader import GradeResult, Simulation

COVER_RE = re.compile(r"^\s*(\w+)\s*:\s*cover\b", re.M)
MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.M)
REQUIREMENT_TYPES = ("DOC", "README")


@dataclass
class GateResult:
    gate: str
    ok: bool | None | str      # True, False, None (unverified) or "n/a"
    detail: str = ""
    data: dict = field(default_factory=dict)


def cover_labels(design: Design) -> dict[str, list[str]]:
    """label -> modules it appears in, across all cover files."""
    out: dict[str, list[str]] = {}
    for f in design.covers:
        text = f.read_text()
        # Assign each label to the closest preceding `module` declaration.
        mods = [(m.start(), m.group(1)) for m in MODULE_RE.finditer(text)]
        for c in COVER_RE.finditer(text):
            mod = [name for pos, name in mods if pos < c.start()][-1:] or ["?"]
            out.setdefault(c.group(1), []).append(mod[0])
    return out


def cover_sync(item: PlanItem, labels: dict[str, list[str]]) -> GateResult:
    mods = labels.get(item.cover, [])
    ok = mods == [item.cover_module]
    return GateResult("cover_sync", ok, "" if ok else f"label {item.cover!r} found in modules {mods}")


def citations(design: Design, item: PlanItem, store: cit.DocStore,
              base_points: list) -> GateResult:
    """data["verified"]: (source, verified ok) per plan source, for the value gate."""
    results, verified = [], []
    for src in item.sources:
        r = None
        if src["type"] in ("RTL", "README"):
            r = cit.check_file_anchor(design.repo_root, item.id, src)
        elif src["type"] == "DOC":
            r = cit.check_doc(store, item.id, src)
        elif src["type"] == "BASE":
            r = cit.check_base(base_points, item.id, src)
        if r:
            results.append(r)
        verified.append((src, r.ok if r else None))
    if not results:
        return GateResult("citations", False, "no sources", {"verified": verified})
    failed = [r for r in results if r.ok is False]
    unverified = [r for r in results if r.ok is None]
    ok = False if failed else (None if unverified else True)
    return GateResult("citations", ok, "; ".join(f"{r.kind} {r.detail}" for r in failed + unverified),
                      {"verified": verified})


def baseline(item: PlanItem, baselines: dict[str, Simulation]) -> GateResult:
    bad = [f"{n}: status {s.sim.status}" for n, s in baselines.items() if s.sim.status != "ok"]
    hit = [f"{n}: {s.plan_hits[item.id]} hits" for n, s in baselines.items() if s.plan_hits[item.id] > 0]
    return GateResult("baseline", not bad and not hit, "; ".join(bad + hit))


def gold(item: PlanItem, a: GradeResult | None) -> GateResult:
    if a is None:
        return GateResult("gold", False, f"missing gold/{item.id}.sv")
    return GateResult("gold", a.reward == 1.0,
                      f"status {a.status}, hits {a.target_hits[item.id]}"
                      + (f"\n{a.diagnostics[-600:]}" if a.reward != 1.0 else ""))


def determinism(a: GradeResult | None, b: GradeResult | None) -> GateResult:
    if a is None or b is None:
        return GateResult("determinism", None, "no gold")
    strip = lambda r: {k: v for k, v in json.loads(r.to_json()).items() if k not in ("compile_s", "run_s")}
    return GateResult("determinism", strip(a) == strip(b))


def near_miss(item: PlanItem, results: list[tuple[str, GradeResult]]) -> GateResult:
    if not results:
        return GateResult("near_miss", "n/a")
    wrong = [f"{n}: status {r.status}, hits {r.target_hits[item.id]}"
             for n, r in results if r.status != "ok" or r.target_hits[item.id] != 0]
    return GateResult("near_miss", not wrong, "; ".join(wrong) or f"{len(results)} near-miss TBs miss")


def source_label(src: dict) -> str:
    where = src.get("file") or src.get("doc") or src.get("point")
    at = f"lines {src['lines']}" if "lines" in src else f"page {src['page']}" if "page" in src else ""
    return " ".join(str(x) for x in (src["type"], where, at) if x)


def value(kills: list[str], only: list[str], verified: list[tuple[dict, bool | None]]) -> GateResult:
    """verified: (source, citation verified) per plan source. Only verified DOC or
    README sources with role: requirement count; RTL and BASE say what the
    design does, not what it must do.
    """
    spec = [source_label(s) for s, ok in verified
            if s.get("role") == "requirement" and s["type"] in REQUIREMENT_TYPES and ok is True]
    evidence = {(True, True): "both", (True, False): "mutant",
                (False, True): "spec", (False, False): "none"}[(bool(kills), bool(spec))]
    return GateResult(
        "value", evidence != "none",
        f"evidence {evidence}; kills {len(kills)} baseline survivors"
        + (f" ({len(only)} only by this gold: {', '.join(only)})" if only else "")
        + f"; requirements: {'; '.join(spec) or '-'}",
        {"evidence": evidence, "kills": kills, "only_by_this_gold": only, "requirements": spec})


def duplicate(corpus: dict[str, dict[str, int]], ids: list[str],
              kills: dict[str, list[str]]) -> tuple[dict[str, GateResult], dict]:
    """corpus: testbench -> plan_hits, only for runs with status ok.

    Returns a result per item and the reported (not enforced) summary.
    """
    sig = {i: {tb for tb, h in corpus.items() if h[i] > 0} for i in ids}
    implies = {i: [j for j in ids if j != i and corpus.get(f"gold:{i}", {}).get(j, 0) > 0]
               for i in ids}
    same_kills = {i: [j for j in ids if j != i and kills.get(i) and kills.get(i) == kills.get(j)]
                  for i in ids}
    out = {}
    for i in ids:
        if f"gold:{i}" not in sig[i]:
            out[i] = GateResult("duplicate", None, "no gold that hits this item")
            continue
        same = [j for j in ids if j != i and sig[j] == sig[i]]
        notes = [f"implies {', '.join(implies[i])}"] if implies[i] else []
        notes += [f"same mutant kills as {', '.join(same_kills[i])}"] if same_kills[i] else []
        head = [f"no testbench separates it from {', '.join(same)}"] if same else []
        out[i] = GateResult("duplicate", not same, "; ".join(head + notes))
    return out, {"implies": {i: v for i, v in implies.items() if v},
                 "same_mutant_kills": {i: v for i, v in same_kills.items() if v}}


def mutation_runs(design: Design, golds: dict[str, Path], pool, cache_path: Path) -> dict:
    """Run the mutants against the baselines, then the golds against the survivors.

    Not a gate: the kills are evidence for the value gate and feed the survivor
    bookkeeping. Every testbench runs only against mutants of modules it
    instantiates. Golds skip mutants a baseline already kills: every output
    here is computed from survivors or from baseline kills.
    """
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    ms = [m for f, (lo, hi) in design.mutate.items() for m in mutants.generate(f, lo, hi)]
    tbs = {f"baseline:{n}": (b["file"].read_text(), b["top"]) for n, b in design.baselines.items()}
    tbs.update({f"gold:{i}": (p.read_text(), "tb") for i, p in golds.items()})

    run = lambda tb, m=None: pool.submit(mutants.simulate, design, *tbs[tb], m, cache=cache)
    orig = {tb: f.result() for tb, f in {tb: run(tb) for tb in tbs}.items()}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    save = lambda: cache_path.write_text(json.dumps(dict(cache), indent=1, sort_keys=True) + "\n")
    status: dict[tuple[str, str], str] = {}

    def collect(futs: dict, phase: str) -> None:
        keys = {f: k for k, f in futs.items()}
        for n, f in enumerate(as_completed(keys), 1):
            status[keys[f]] = f.result()["status"]
            if n % 20 == 0 or n == len(keys):  # an interrupted run keeps what it computed
                save()
                print(f"mutation {phase}: {n}/{len(keys)}", file=sys.stderr, flush=True)
        save()

    runnable = lambda tb, pool_ms: {(tb, m.id): run(tb, m) for m in pool_ms
                                    if orig[tb]["status"] == "ok" and m.module in orig[tb]["modules"]}
    collect({k: f for tb in tbs if tb.startswith("baseline:") for k, f in runnable(tb, ms).items()},
            "baselines")
    stillborn = {mid for (_, mid), st in status.items() if st in ("compile_error", "compile_timeout")}
    base_killed = {mid for (tb, mid), st in status.items() if st != "ok"} - stillborn
    survivors = [m for m in ms if m.id not in stillborn and m.id not in base_killed]
    collect({k: f for tb in tbs if tb.startswith("gold:") for k, f in runnable(tb, survivors).items()},
            "golds")
    stillborn = sorted({mid for (_, mid), st in status.items() if st in ("compile_error", "compile_timeout")})

    killed_by = {m.id: {tb for (tb, mid), st in status.items() if mid == m.id and st != "ok"}
                 for m in ms if m.id not in stillborn}
    surv = {mid for mid, k in killed_by.items() if not any(tb.startswith("baseline:") for tb in k)}
    waivers = design.waivers.get("mutants", {}) or {}
    gold_kills = {mid for mid in surv if killed_by[mid]}

    per_gold, only_gold = {}, {}
    for i in golds:
        tb = f"gold:{i}"
        if orig[tb]["status"] == "ok":
            per_gold[i] = sorted(mid for mid in surv if tb in killed_by[mid])
            only_gold[i] = [mid for mid in per_gold[i] if killed_by[mid] == {tb}]

    valid = len(killed_by)
    n_base_killed = valid - len(surv)
    return {
        "mutants": len(ms), "stillborn": stillborn, "valid": valid,
        "baseline_killed": n_base_killed,
        "baseline_score": round(n_base_killed / valid, 3) if valid else None,
        "baseline_plus_gold_score": round((n_base_killed + len(gold_kills)) / valid, 3) if valid else None,
        "survivors_killed_by_gold": sorted(gold_kills),
        "gold_kills": per_gold,  # item -> baseline survivors its gold kills
        "only_gold_kills": only_gold,  # ... that no other testbench kills
        "waived": sorted(surv & set(waivers)),
        "unexplained": sorted(surv - gold_kills - set(waivers)),
        # A waiver claims the mutant is equivalent; a kill disproves it.
        "bad_waivers": sorted(mid for mid in waivers if mid not in killed_by or killed_by[mid]),
        "golds_checked": sorted(tb for tb in tbs if tb.startswith("gold:")),
    }
