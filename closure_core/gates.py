"""Gates: the mechanical checks a plan item must pass before it can be a task.

Each gate is a function of simulation results (from grader.grade/simulate)
that returns a GateResult. Running the simulations is left to the caller, so
tools/check can run everything in parallel while tools/gate_candidate runs
gates one at a time, cheapest first, stopping at the first failure.

  citations     every cited source verifies (RTL/README anchors, DOC page+hash, BASE point)
  cover_sync    exactly one cover with the item's label, in the module the plan names
  cover_policy  the cover file only observes: allowlisted constructs, one module
                cov_<ID>, one bind (closure_core/policy.py, on Verilator's AST)
  description_sync  every design signal and sized/hex constant the description
                names is read by the cover (a port declared but never read
                does not count): the description cannot promise what the
                grader does not check. Names and constants only.
  baseline      no baseline testbench hits the item (the task is not free)
  gold          the gold testbench scores 1 (the task is solvable)
  near_miss     at least one near-miss testbench, and every one scores 0 (the
                boundary is exact); an item may instead give a
                near_miss_waiver, a written reason why no near-miss is
                meaningful, which passes and is always audited
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
  duplicate     some testbench we run (baseline, random, gold, near-miss) hits this item
                and not the other, for every other item compared. A signature
                is the set of testbenches that hit an item; adding testbenches
                can only split signatures, never merge them. Reported, not
                enforced: implications (this gold also hits item X) and items
                whose golds kill the same baseline-surviving mutants.

Reported, not gates: which items the fixed-seed random testbenches hit
(random_hits: reachable by accident), and the baseline coverage holes each
gold closes (holes, waived_holes).

No gate calls a model. Solvability from the agent's view is established by the
pilot; items no pilot model solves get a fairness check (docs/PLAN.md §6).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from concurrent.futures import as_completed
from dataclasses import dataclass, field
from pathlib import Path

from closure_core import citations as cit
from closure_core import mutants, policy
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


def parse_cover(design: Design, item: PlanItem) -> tuple[policy.Ast | None, str]:
    """One parse of the RTL and the item's cover, shared by cover_policy and description_sync."""
    root, log = policy.xml_ast([*map(str, design.rtl), str(design.pack / "covers" / f"{item.id}.sv")])
    return (policy.Ast(root) if root is not None else None), log


def cover_policy(design: Design, item: PlanItem, parsed: tuple | None = None) -> GateResult:
    ast, log = parsed or parse_cover(design, item)
    if ast is None:
        return GateResult("cover_policy", False, f"verilator --xml-only failed:\n{log[-1500:]}")
    rtl = [str(p) for p in design.rtl]
    vs = policy.check_cover(ast, str(design.pack / "covers" / f"{item.id}.sv"), item.id, rtl)
    return GateResult("cover_policy", not vs, "\n".join(map(str, vs)), {"violations": [str(v) for v in vs]})


def description_sync(design: Design, item: PlanItem, parsed: tuple | None = None) -> GateResult:
    """Every design signal and sized/hex constant the description names is read by the cover."""
    ast, log = parsed or parse_cover(design, item)
    if ast is None:
        return GateResult("description_sync", False, f"verilator --xml-only failed:\n{log[-1500:]}")
    missing = policy.check_description(ast, str(design.pack / "covers" / f"{item.id}.sv"), item.id,
                                       [str(p) for p in design.rtl], item.description)
    return GateResult("description_sync", not missing, "\n".join(
        f"the description names {x} but the cover does not check it; either check it in the cover "
        f"or remove it from the description" for x in missing), {"missing": missing})


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


def baseline(item: PlanItem, baselines: dict[str, Simulation],
             randoms: dict[str, Simulation] | None = None) -> GateResult:
    bad = [f"{n}: status {s.sim.status}" for n, s in baselines.items() if s.sim.status != "ok"]
    hit = [f"{n}: {s.plan_hits[item.id]} hits" for n, s in baselines.items() if s.plan_hits[item.id] > 0]
    rnd = random_hits(item, randoms or {})
    note = [f"hit by random stimulus ({', '.join(f'{n}: {h}' for n, h in rnd.items())})"] if rnd else []
    return GateResult("baseline", not bad and not hit, "; ".join(bad + hit + note), {"hit_by_random": rnd})


def random_hits(item: PlanItem, randoms: dict[str, Simulation]) -> dict[str, int]:
    """Hits per random testbench (status ok only): reported, never a failure."""
    return {n: s.plan_hits[item.id] for n, s in randoms.items()
            if s.sim.status == "ok" and s.plan_hits[item.id] > 0}


CODE_KINDS = ("v_line", "v_branch", "v_toggle")


def point_key(p) -> str:
    return f"{p.kind} {Path(p.file).name}:{p.line} {p.name}"


def holes(baselines: dict[str, Simulation]) -> list[str]:
    """Design (RTL) line/branch/toggle points no baseline hits."""
    best: dict[str, int] = {}
    for s in baselines.values():
        for p in s.points:
            if p.kind in CODE_KINDS and "/rtl/" in p.file:
                best[point_key(p)] = max(best.get(point_key(p), 0), p.hits)
    return sorted(k for k, h in best.items() if h == 0)


def hit_points(s: Simulation) -> set[str]:
    return {point_key(p) for p in s.points if p.kind in CODE_KINDS and "/rtl/" in p.file and p.hits > 0}


def waived_holes(design: Design) -> dict[str, str]:
    """waivers.yaml holes: point key -> waiver ID. `bits: [lo, hi]` expands a vector toggle."""
    out = {}
    for w in design.waivers.get("holes", []) or []:
        for p in w["points"]:
            names = ([f"{p['name']}[{b}]" for b in range(p["bits"][0], p["bits"][1] + 1)]
                     if "bits" in p else [p["name"]])
            out.update({f"{p['kind']} {p['file']}:{p['line']} {n}": w["id"] for n in names})
    return out


def testbench_policy(design: Design, tb: Path, *, gold: bool) -> list[str]:
    """Policy violations of one of our testbenches (gold or near-miss)."""
    ours = [*design.rtl, *design.covers]
    root, log = policy.parse_testbench(tb, ours, extra=policy.TESTBENCH_FLAGS)
    if root is None:
        return [f"verilator --xml-only failed:\n{log[-1500:]}"]
    check = policy.check_gold if gold else policy.check_testbench
    return [str(v) for v in check(policy.Ast(root), str(tb), policy.module_names(ours))]


def gold(item: PlanItem, a: GradeResult | None, violations: list[str] = ()) -> GateResult:
    if a is None:
        return GateResult("gold", False, f"missing gold/{item.id}.sv")
    if violations:
        return GateResult("gold", False, "policy: " + "\n".join(violations))
    return GateResult("gold", a.reward == 1.0,
                      f"status {a.status}, hits {a.target_hits[item.id]}"
                      + (f"\n{a.diagnostics[-600:]}" if a.reward != 1.0 else ""))


def determinism(a: GradeResult | None, b: GradeResult | None) -> GateResult:
    if a is None or b is None:
        return GateResult("determinism", None, "no gold")
    strip = lambda r: {k: v for k, v in json.loads(r.to_json()).items() if k not in ("compile_s", "run_s")}
    return GateResult("determinism", strip(a) == strip(b))


NEAR_MISS_OVERLAP = 0.9  # reported, not enforced; arbitrary until we have data


def line_overlap(gold_sim: Simulation, other: Simulation) -> float | None:
    """Share of the design lines the gold hits that `other` also hits.

    A real near-miss exercises nearly the gold's path and only misses the
    boundary; one that does nothing passes the near-miss gate vacuously.
    """
    lines = lambda s: {(Path(p.file).name, p.line, p.name) for p in s.points
                       if p.kind == "v_line" and p.hits > 0 and "/rtl/" in p.file}
    g = lines(gold_sim)
    return round(len(g & lines(other)) / len(g), 3) if g else None


def near_miss(item: PlanItem, results: list[tuple[str, GradeResult]],
              violations: dict[str, list[str]] | None = None,
              overlap: dict[str, float | None] | None = None) -> GateResult:
    if not results:
        if item.near_miss_waiver:
            return GateResult("near_miss", True, f"opted out (audited): {item.near_miss_waiver}",
                              {"opted_out": item.near_miss_waiver})
        return GateResult("near_miss", False, "no near-miss testbench; add one, or a near_miss_waiver "
                                              "with the reason no near-miss is meaningful")
    if item.near_miss_waiver:
        return GateResult("near_miss", False, "near_miss_waiver given but near-miss testbenches exist")
    bad = [f"{n}: policy: {'; '.join(v)}" for n, v in (violations or {}).items() if v]
    wrong = [f"{n}: status {r.status}, hits {r.target_hits[item.id]}"
             for n, r in results if r.status != "ok" or r.target_hits[item.id] != 0]
    overlap = overlap or {}
    low = [n for n, o in overlap.items() if o is not None and o < NEAR_MISS_OVERLAP]
    notes = [f"{n}: covers {overlap[n]:.0%} of the gold's design lines (low: may pass vacuously)"
             for n in low]
    detail = "; ".join(bad + wrong) or f"{len(results)} near-miss TBs miss"
    return GateResult("near_miss", not (bad or wrong), "; ".join([detail, *notes]),
                      {"overlap": overlap, "low_overlap": low})


def source_label(src: dict) -> str:
    where = src.get("file") or src.get("doc") or src.get("point")
    at = f"lines {src['lines']}" if "lines" in src else f"page {src['page']}" if "page" in src else ""
    return " ".join(str(x) for x in (src["type"], where, at) if x)


def value(kills: list[str], only: list[str], verified: list[tuple[dict, bool | None]]) -> GateResult:
    """verified: (source, citation verified) per plan source. Only verified DOC or
    README sources with role: requirement count; RTL and BASE say what the
    design does, not what it must do.
    """
    reqs = [s for s, ok in verified
            if s.get("role") == "requirement" and s["type"] in REQUIREMENT_TYPES and ok is True]
    spec = [source_label(s) for s in reqs]
    evidence = {(True, True): "both", (True, False): "mutant",
                (False, True): "spec", (False, False): "none"}[(bool(kills), bool(spec))]
    return GateResult(
        "value", evidence != "none",
        f"evidence {evidence}; kills {len(kills)} baseline survivors"
        + (f" ({len(only)} only by this gold: {', '.join(only)})" if only else "")
        + f"; requirements: {'; '.join(spec) or '-'}",
        {"evidence": evidence, "kills": kills, "only_by_this_gold": only, "requirements": spec,
         "requirement_keys": [requirement_key(s) for s in reqs]})


def requirement_key(src: dict) -> str:
    """One cited requirement sentence: where it is and its anchor."""
    return f'{source_label(src)} "{src.get("anchor", "")}"'


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


def save_cache(path: Path, cache: dict) -> None:
    """Atomic: parallel gate runs (tools/propose_plan -p) share this file. A lost
    update only costs a re-simulation; a torn read would crash a run. The temp
    name is unique per call: every container is PID 1, so a pid suffix collides."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(dict(cache), indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


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
    save = lambda: save_cache(cache_path, cache)
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
