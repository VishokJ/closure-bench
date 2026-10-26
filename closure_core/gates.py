"""Gates: the mechanical checks a plan item must pass before it can be a task.

Each gate is a function of simulation results (from grader.grade/simulate)
that returns a GateResult. Running the simulations is left to the caller, so
tools/check can run everything in parallel while tools/gate_candidate runs
gates one at a time, cheapest first, stopping at the first failure.

  mechanism     each declared difficulty mechanism (boundary, sequence, interaction,
                data, reset_timing) is structurally there; at least two
                required in target-only proposer runs, checked whenever declared
  citations     every cited source verifies (RTL/README anchors, DOC page+hash, BASE point)
  formal        only for a candidate without its own gold (or with a twin.sv):
                closure_core.formal.cover_witness must find a witness for the
                target cover; the witness testbench becomes the item's reach
                gold, which the gold gate then scores under Verilator (formal
                measures, Verilator judges). A twin cover (the off-by-one
                condition) must be reachable too; its witness becomes a
                near-miss that must score 0. Optional minimum witness depth.
  cover_sync    exactly one cover with the item's label, in the module the plan names
  cover_policy  the cover file only observes: allowlisted constructs, one module
                cov_<ID>, one bind (closure_core/policy.py, on Verilator's AST)
  description_sync  every design signal and sized/hex constant the description
                names is read by the cover (a port declared but never read
                does not count): the description cannot promise what the
                grader does not check. Names and constants only.
  baseline      no baseline testbench hits the item (the task is not free)
  gold          the gold testbench scores 1 (the task is solvable). Two roles:
                a checking gold (written by a person or the proposer) must
                $fatal when the behaviour is wrong; a reach gold (a formal
                witness, first line REACH_HEADER) only has to reach it
  near_miss     at least one near-miss testbench, and every one scores 0 (the
                boundary is exact); a composed item (composed_from) also
                inherits its components' golds and near-misses
                (composed_near_misses); an item may instead give a
                near_miss_waiver, a written reason why no near-miss is
                meaningful, which passes and is always audited
  determinism   grading the gold twice gives an identical result
  value         evidence the item matters, either kind is enough:
                mutant: the gold kills at least one mutant every baseline
                  survives (closure_core/mutants.py; a kill = passes on the
                  original RTL, fails on the mutant);
                spec: a verified DOC or README source with role: requirement
                  (a composed item, composed_from, also inherits its
                  components' verified requirements).
                Only checking golds run against mutants: a reach gold checks
                nothing, so it cannot kill one.
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

import ast
import fcntl
import functools
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from closure_core import citations as cit
from closure_core import legality, mutants, policy
from closure_core.infra import InfraError
from closure_core.design import Design, PlanItem
from closure_core.grader import GradeResult, Simulation

COVER_RE = re.compile(r"^\s*(\w+)\s*:\s*cover\b", re.M)
MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.M)
REQUIREMENT_TYPES = ("DOC", "README")
# Shared by every worktree and run on this machine, next to the cited PDFs (citations.CACHE):
# the Docker executor mounts this folder, the Prime executor uploads it and merges it back.
CACHE_DIR = Path.home() / ".cache" / "closure-bench"
MUTATION_CACHE = CACHE_DIR / "mutation_cache.json"
WITNESSES = CACHE_DIR / "witnesses"


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


MECHANISMS = ("boundary", "sequence", "interaction", "data", "reset_timing")
RESET_TIMING_CAP = 2  # accepted items declaring reset_timing per proposer run (set stage)
MIN_MECHANISMS = 2    # distinct mechanisms per target when required (target-only runs)
_WIDE_LITERAL = re.compile(r"(?<![\w'])(\d*)'[sS]?[hHdDbBoO][0-9a-fA-F_]+\b|\b0[xX][0-9a-fA-F_]+\b")


def declared_mechanisms(raw: dict) -> list:
    """item.yaml `mechanism`: one name or a list of names."""
    m = raw.get("mechanism")
    return [] if m is None else list(m) if isinstance(m, list) else [m]


def mechanism(design: Design, item: PlanItem, raw: dict, has_twin: bool, parsed: tuple | None = None,
              required: bool = False) -> GateResult:
    """The declared difficulty mechanisms (item.yaml `mechanism`), each checked where cheap.

    boundary     a twin cover (or a near_miss_waiver) shows the off-by-one side
    sequence     the cover keeps a tracking register of its own
    interaction  the cover reads at least two design signals besides clk and rst
    data         the cover compares against a multi-bit constant (8'h55, 0xA5)
    reset_timing declared only; at most RESET_TIMING_CAP per run (propose set stage)
    Required only in target-only runs, then at least MIN_MECHANISMS distinct ones;
    checked whenever declared. Every failing mechanism is reported at once.
    """
    ms = declared_mechanisms(raw)
    if not ms:
        return GateResult("mechanism", False if required else "n/a",
                          f"declare mechanism: a list of at least {MIN_MECHANISMS} of {', '.join(MECHANISMS)}"
                          if required else "not declared")
    bad = [m for m in ms if m not in MECHANISMS]
    if bad:
        return GateResult("mechanism", False, f"mechanism {bad} must each be one of {', '.join(MECHANISMS)}")
    if len(set(ms)) != len(ms):
        return GateResult("mechanism", False, f"mechanism {ms} lists one twice")
    if required and len(ms) < MIN_MECHANISMS:
        return GateResult("mechanism", False, f"mechanism {ms}: combine at least {MIN_MECHANISMS} distinct "
                                              f"mechanisms (of {', '.join(MECHANISMS)})")
    ast, log = parsed or parse_cover(design, item)
    if ast is None:
        return GateResult("mechanism", False, f"verilator --xml-only failed:\n{log[-1500:]}")
    cover_file = str(design.pack / "covers" / f"{item.id}.sv")
    cover = next((x for x in ast.defined_in(cover_file) if x.get("name") == item.cover_module), None)
    vars_ = [v for v in cover if v.tag == "var"] if cover is not None else []
    inputs = {v.get("name") for v in vars_ if v.get("dir") == "input"}
    read = ({n.get("name") for n in cover.iter("varref")} & inputs) - {"clk", "rst"} if cover is not None else set()
    local = [v.get("name") for v in vars_ if v.get("dir") is None and not (v.get("param") or v.get("localparam"))
             and not v.get("name", "").startswith("_V")]  # _Vpast_*: generated by $past
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", (design.pack / "covers" / f"{item.id}.sv").read_text(), flags=re.S)
    wide = [x.group(0) for x in _WIDE_LITERAL.finditer(text) if x.group(1) != "1"]
    rules = {
        "boundary": None if has_twin or item.near_miss_waiver else
                    "boundary needs a twin cover (twin.sv) for the off-by-one condition",
        "sequence": None if local else "sequence needs a tracking register in the cover (a local reg)",
        "interaction": None if len(read) >= 2 else
                       f"interaction needs the cover to read two or more design signals besides clk/rst; "
                       f"it reads {sorted(read) or 'none'}",
        "data": None if wide else "data needs the cover to compare against a multi-bit constant (e.g. 8'h55)",
        "reset_timing": None,
    }
    why = [rules[m] for m in ms if rules[m]]
    return GateResult("mechanism", not why, "; ".join(why) or ", ".join(ms),
                      {"mechanisms": ms, "reads": sorted(read), "locals": local, "constants": wide})


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


def legality_citations(design: Design, store: cit.DocStore) -> GateResult:
    """Every legality rule's cited sources verify (RTL/README anchors, DOC page and hash)."""
    results = []
    for r in design.legality.rules:
        for src in r.sources:
            if src["type"] in ("RTL", "README"):
                results.append(cit.check_file_anchor(design.repo_root, r.id, src))
            elif src["type"] == "DOC":
                results.append(cit.check_doc(store, r.id, src))
            else:
                results.append(cit.CitationResult(r.id, src["type"], False, "a rule cites RTL, README or DOC only"))
    failed = [r for r in results if r.ok is False]
    unverified = [r for r in results if r.ok is None]
    return GateResult("legality_citations", False if failed else (None if unverified else True),
                      "; ".join(f"{r.item}: {r.kind} {r.detail}" for r in failed + unverified)
                      or f"{len(results)} sources verified")


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


REACH_HEADER = "// gold_source: formal"  # first line of every reach gold; nothing else may use it


def gold_source(tb: Path) -> str:
    """'formal' for a reach gold (a formal witness), 'llm' for a checking gold."""
    return "formal" if tb.read_text().startswith(REACH_HEADER + "\n") else "llm"


def testbench_policy(design: Design, tb: Path, *, gold: bool) -> list[str]:
    """Policy violations of one of our testbenches (gold or near-miss)."""
    ours = [*design.rtl, *design.covers]
    root, log = policy.parse_testbench(tb, ours, extra=policy.TESTBENCH_FLAGS)
    if root is None:
        return [f"verilator --xml-only failed:\n{log[-1500:]}"]
    ast, reserved = policy.Ast(root), policy.module_names(ours)
    if not gold:
        return [str(v) for v in policy.check_testbench(ast, str(tb), reserved)]
    role = "reach" if gold_source(tb) == "formal" else "checking"
    return [str(v) for v in policy.check_gold(ast, str(tb), reserved, role=role)]


def gold(item: PlanItem, a: GradeResult | None, violations: list[str] = ()) -> GateResult:
    if a is None:
        return GateResult("gold", False, f"missing gold/{item.id}.sv")
    if violations:
        return GateResult("gold", False, "policy: " + "\n".join(violations))
    return GateResult("gold", a.reward == 1.0,
                      f"status {a.status}, hits {a.target_hits[item.id]}"
                      + (f"\n{a.diagnostics[-600:]}" if a.reward != 1.0 else ""))


# --- formal ---------------------------------------------------------------------------------

FORMAL_DIR = "formal"  # the pack's formal environment: formal.yaml (tops, engine, bound, timeouts) + env files


class FormalError(InfraError):
    """Infrastructure failure (no formal tools, sby crashed, no environment): not a
    decision about the candidate. The gate aborts; nothing is cached or counted."""


def formal_dir(design: Design) -> Path:
    return design.pack / FORMAL_DIR


def formal_settings(design: Design) -> dict:
    """engine, bound (cycles), timeout and minimize_timeout (seconds) for cover_witness,
    from formal.yaml; and frame_cycles, the design's frame length expression, and
    active_signal, the output that marks protocol activity (None if not set)."""
    f = formal_dir(design) / "formal.yaml"
    spec = yaml.safe_load(f.read_text()) if f.is_file() else None
    if not isinstance(spec, dict) or not {"engine", "bound", "timeout", "minimize_timeout"} <= set(spec):
        raise FormalError(f"{f} must exist and set engine, bound, timeout and minimize_timeout")
    fc = spec.get("frame_cycles")
    return {"engine": str(spec["engine"]), "bound": int(spec["bound"]), "timeout": float(spec["timeout"]),
            "minimize_timeout": float(spec["minimize_timeout"]),
            "frame_cycles": None if fc is None else str(fc), "active_signal": spec.get("active_signal")}


_ARITH = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
          ast.FloorDiv: lambda a, b: a // b}


def _eval_cycles(expr: str, values: dict[str, int]) -> int:
    """formal.yaml frame_cycles (integers, input names, + - * //) at one cycle's inputs."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and type(n.value) is int:
            return n.value
        if isinstance(n, ast.Name) and n.id in values:
            return values[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _ARITH:
            return _ARITH[type(n.op)](ev(n.left), ev(n.right))
        raise ValueError(f"frame_cycles {expr!r}: only integers, input names and + - * // are allowed")
    return ev(ast.parse(expr, mode="eval"))


_TB_DECL = re.compile(r"^\s*logic\s+(?:\[\d+:0\]\s+)?(\w+)\s*=\s*\d+'d(\d+);\s*$")
_TB_WAIT = re.compile(r"^\s*(?:repeat \((\d+)\) )?@\(negedge clk\);\s*$")
_TB_SET = re.compile(r"(\w+) = \d+'d(\d+);")


def witness_frames(tb_text: str, depth: int, frame_cycles: str) -> float:
    """Elapsed time of a witness in frames: the sum over its `depth` cycles of
    1 / frame_cycles(inputs at that cycle). A witness at prescale 2 then counts
    the same as its prescale-1 equivalent, so slowing the clock never deepens a
    target; waiting the cover itself demands still counts.

    Reads the testbench formal.witness_testbench writes: step 0 from the
    declarations, `repeat (n) @(negedge clk);` advances n steps, the assignments
    after it hold from that step on; the trailing padding after the last step
    is not counted. Raises ValueError on anything else.
    """
    values: dict[str, int] = {}
    step, changes = 0, []
    for line in tb_text.splitlines():
        if m := _TB_DECL.match(line):
            values[m.group(1)] = int(m.group(2))
        elif m := _TB_WAIT.match(line):
            if not changes:
                changes.append((0, dict(values)))
            step += int(m.group(1) or 1)
        elif sets := _TB_SET.findall(line):
            if not changes:
                raise ValueError("witness testbench: an assignment before the first wait")
            values.update({n: int(v) for n, v in sets})
            changes.append((step, dict(values)))
    if not changes:
        raise ValueError("witness testbench: no stimulus found")
    total = 0.0
    for (start, vals), (end, _) in zip(changes, [*changes[1:], (depth, None)]):
        n = min(end, depth) - min(start, depth)
        if n > 0:
            c = _eval_cycles(frame_cycles, vals)
            if c <= 0:
                raise ValueError(f"frame_cycles {frame_cycles!r} is {c} at {vals}")
            total += n / c
    return total


def formal_files(design: Design) -> dict[str, str]:
    """Every file of the formal environment (the assumptions), by path within it."""
    d = formal_dir(design)
    return {str(q.relative_to(d)): q.read_text() for q in sorted(d.rglob("*")) if q.is_file()} if d.is_dir() else {}


@functools.lru_cache(maxsize=1)
def formal_version() -> str | None:
    """`yosys -V` of the formal tools (closure_core.formal.FORMAL_HOME), None if they
    are not installed. If they are but the call fails (e.g. a timeout under load),
    FormalError: a silent None would change every witness key, so the cache would
    miss and a replay would re-solve. Not cached when it raises."""
    try:
        home = importlib.import_module("closure_core.formal").FORMAL_HOME
    except (ImportError, AttributeError):
        return None
    yosys = home / "bin" / "yosys"
    if not yosys.exists():
        return None
    try:
        out = subprocess.run([str(yosys), "-V"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        raise FormalError(f"yosys -V failed: {e}") from e
    if not out:
        raise FormalError("yosys -V printed nothing")
    return out


_YOSYS_RELEASE = re.compile(r"^(Yosys \S+ \(git sha1 [0-9a-f]+)")


def tools_release(version: str | None) -> str | None:
    """`yosys -V` without its build info: the version and source revision, the same
    for every architecture of one OSS CAD Suite release (arm64 says GNU g++, x86_64
    Clang). An unrecognised string is kept whole: a distinct key, never a false hit."""
    m = _YOSYS_RELEASE.match(version or "")
    return m.group(1) + ")" if m else version


def witness_key(design: Design, cover_text: str, allow: tuple[str, ...] = ()) -> str:
    """What a witness depends on: the cover, the RTL, the whole formal environment
    (search restrictions, engine, bound, timeouts), the legality assumptions formal
    generates for this allow list, and the formal tools' release (tools_release), so a
    witness solved on arm64 is reused on x86_64 and the other way round.

    Not the rest of the pack, so the set stage (a different pack, same design)
    reuses the witness found for the candidate alone.
    """
    return hashlib.sha256(json.dumps({
        "cover": cover_text, "rtl": {q.name: q.read_text() for q in design.rtl},
        "formal": formal_files(design), "tools": tools_release(formal_version()),
        "legality": legality.assume_text(design.legality, legality.enforced(design.legality, [tuple(allow)])),
    }, sort_keys=True).encode()).hexdigest()


def solve_witness(design: Design, cover: Path, allow: tuple[str, ...] = ()) -> dict:
    """The only call into closure_core.formal: cover_witness(pack_dir, cover_file, *, bound, timeout,
    engine, minimize_timeout, allow), all from formal.yaml but allow (the item's legality allow list).

    UnsupportedCover and ValueError are decisions about the cover (statuses
    'unsupported' and 'invalid'); RuntimeError and missing tools raise FormalError.
    """
    try:
        formal_mod = importlib.import_module("closure_core.formal")
    except ImportError as e:
        raise FormalError(f"closure_core.formal unavailable: {e}") from e
    st = formal_settings(design)
    try:
        w = formal_mod.cover_witness(design.pack, cover, bound=st["bound"], timeout=st["timeout"],
                                     engine=st["engine"], minimize_timeout=st["minimize_timeout"],
                                     allow=tuple(allow))
    except formal_mod.UnsupportedCover as e:  # a ValueError: caught first
        return {"status": "unsupported", "detail": str(e)}
    except ValueError as e:
        return {"status": "invalid", "detail": str(e)}
    except RuntimeError as e:
        raise FormalError(f"cover_witness failed: {e}") from e
    return {**w, "detail": w.get("detail") or ""}


TIMEOUT_DETAIL = "target too hard to verify within the time budget: simplify one mechanism or reduce depth"


@contextmanager
def formal_slot(cache_dir: Path | None, exclusive: bool):
    """A POSIX lock on <cache_dir>/.formal.lock. Every solve holds it shared; the
    retry of a timeout holds it exclusive, so it runs with no other formal job of
    the run, across the run's containers (lockf, not flock: flock does not exclude
    across containers on a Docker Desktop bind mount, lockf does; checked). POSIX
    locks belong to the process, so this assumes one solve at a time per process,
    as in gate_candidate. Linux gives no writer preference: under a steady stream
    of solves the retry waits until a gap."""
    if cache_dir is None:
        yield
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / ".formal.lock", "a+") as f:
        fcntl.lockf(f, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.lockf(f, fcntl.LOCK_UN)


def witness_store(root: Path = WITNESSES) -> Path | None:
    """The shared witness store for this formal engine: root/<hash of closure_core/formal.py>.
    witness_key leaves the engine's code out (a run's keys must not change with it), so
    a store shared across worktrees and runs is split by it instead. None without formal.py."""
    engine = Path(__file__).with_name("formal.py")
    return root / hashlib.sha256(engine.read_bytes()).hexdigest()[:16] if engine.is_file() else None


def store_witness(store: Path, key: str, w: dict) -> bool:
    """Add a witness to the shared store unless it has one for this key (never overwritten)."""
    dest = store / f"{key}.json"
    with cache_lock(store):
        if dest.exists():
            return False
        store.mkdir(parents=True, exist_ok=True)
        save_cache(dest, w)
        return True


def witness(design: Design, cover: Path, cache_dir: Path | None, store: Path | None = None,
            allow: tuple[str, ...] = ()) -> dict:
    """A cached witness: cache_dir/<key>.json, so a replay never re-solves.
    allow: the item's legality allow list (legality rules formal does not assume).

    A timeout may be load, so it is retried once with no other formal job running
    (formal_slot); only the retry's outcome is cached (`retried: true`). A second
    timeout is a decision: TIMEOUT_DETAIL. Every other outcome cover_witness
    returns is cached as is (reachable, unreachable, unsupported, invalid);
    infrastructure errors raise and are not.

    store: the shared witness store (witness_store()), looked up after cache_dir; a
    hit is copied into cache_dir, so the run keeps every witness it used. Solved
    outcomes go into the store too, except timeouts: they depend on the machine
    and its load, so another run solves them again.
    """
    key = witness_key(design, cover.read_text(), allow)
    path = cache_dir / f"{key}.json" if cache_dir else None
    if path and path.exists():
        return {**json.loads(path.read_text()), "key": key}
    if store and (store / f"{key}.json").exists():
        w = json.loads((store / f"{key}.json").read_text())
    else:
        with formal_slot(cache_dir, exclusive=False):
            w = solve_witness(design, cover, allow)
        if w["status"] == "timeout":
            with formal_slot(cache_dir, exclusive=True):
                w = {**solve_witness(design, cover, allow), "retried": True}
        if store and w["status"] != "timeout":
            store_witness(store, key, w)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        save_cache(path, w)
    return {**w, "key": key}


def twin_label(twin: Path) -> str | None:
    labels = COVER_RE.findall(twin.read_text())
    return labels[0] if len(labels) == 1 else None


def twin_policy(design: Design, twin: Path, item_id: str) -> list[str]:
    """A twin is a cover like any other (module cov_<ID>_twin, one bind), with one label."""
    root, log = policy.xml_ast([*map(str, design.rtl), str(twin)])
    if root is None:
        return [f"verilator --xml-only failed:\n{log[-1500:]}"]
    vs = [str(v) for v in policy.check_cover(policy.Ast(root), str(twin), f"{item_id}_twin",
                                             [str(q) for q in design.rtl])]
    return vs + ([] if twin_label(twin) else ["must contain exactly one cover property"])


def _probe_names(frame_cycles: str) -> list[str]:
    return sorted({n.id for n in ast.walk(ast.parse(frame_cycles, mode="eval")) if isinstance(n, ast.Name)})


def active_probe(tb_text: str, depth: int, signal: str, frame_cycles: str) -> str:
    """The witness testbench plus a probe: at each rising edge t < depth it prints
    `CBA t <signal> <inputs of frame_cycles>` when any of them changed (t = 0
    always), and `CBA_END` at t = depth. Cycle t is the t-th rising edge, as in
    the witness; the signal is read before that edge's update (its value during
    cycle t). Only changes are printed, so the run log's tail holds them."""
    names = [signal, *_probe_names(frame_cycles)]
    last = [f"cb_last{k}" for k in range(len(names))]
    changed = " || ".join(f"{n} != {v}" for n, v in zip(names, last))
    probe = [
        "  // closure-bench probe (gates.active_frames): not part of the witness",
        "  int cb_t = 0;",
        *(f"  longint {v} = 0;" for v in last),
        "  always @(posedge clk) begin",
        f"    if (cb_t < {depth} && (cb_t == 0 || {changed}))",
        f'      $display("CBA %0d{" %0d" * len(names)}", cb_t, {", ".join(names)});',
        f'    if (cb_t == {depth}) $display("CBA_END");',
        *(f"    {v} <= {n};" for n, v in zip(names, last)),
        "    cb_t <= cb_t + 1;",
        "  end",
    ]
    i = tb_text.rindex("endmodule")
    return tb_text[:i] + "\n".join(probe) + "\n" + tb_text[i:]


def active_frames_from_log(log: str, depth: int, signal: str, frame_cycles: str) -> float:
    """Sum over cycles t < depth of signal_t / frame_cycles(inputs_t), from the probe's lines."""
    names = [signal, *_probe_names(frame_cycles)]
    rows = [list(map(int, ln.split()[1:])) for ln in log.splitlines() if ln.startswith("CBA ")]
    if "CBA_END" not in log or not rows or rows[0][0] != 0:
        raise ValueError("probe output incomplete (no CBA_END, or no line for cycle 0)")
    total = 0.0
    for row, nxt in zip(rows, [*rows[1:], [depth]]):
        vals = dict(zip(names, row[1:]))
        if vals[signal]:
            total += (nxt[0] - row[0]) / _eval_cycles(frame_cycles, vals)
    return total


def active_frames(design: Design, w: dict, frame_cycles: str, signal: str) -> dict:
    """{active_frames} of a reachable witness, by simulating it with the probe; a
    measurement only: on failure {active_frames: None, active_frames_error}."""
    from closure_core.infra import simulate
    try:
        s = simulate(design, active_probe(w["tb_text"], w["depth"], signal, frame_cycles))
        if s.sim.status != "ok":
            raise ValueError(f"probe simulation: {s.sim.status}")
        return {"active_frames": round(active_frames_from_log(s.sim.run_log, w["depth"], signal, frame_cycles), 3)}
    except ValueError as e:
        return {"active_frames": None, "active_frames_error": str(e)}


def _summary(w: dict, frame_cycles: str | None = None) -> dict:
    out = {"status": w["status"], "witness_depth": w.get("depth"), "input_changes": w.get("input_changes"),
           "input_changes_exact": w.get("input_changes_exact"), "key": w.get("key")}
    if frame_cycles and w["status"] == "reachable" and w.get("tb_text"):
        try:
            out["witness_frames"] = round(witness_frames(w["tb_text"], w["depth"], frame_cycles), 3)
        except ValueError as e:  # the testbench comes from formal.py, the formula from the pack
            raise FormalError(f"cannot measure the witness in frames: {e}") from e
    return out


def _not_found(what: str, w: dict, where: str) -> str | None:
    """Why there is no witness for `what`, or None if there is one."""
    st = w["status"]
    if st == "reachable" and w.get("tb_text"):
        return None
    if st == "unreachable":
        return (f"{what} is unreachable {where}: no stimulus the environment allows reaches it. Check the "
                f"cover condition against the RTL and the assumptions.")
    if st == "timeout":
        return (f"{TIMEOUT_DETAIL}. Formal timed out twice on {what} {where}, the second time with "
                f"no other formal job running.")
    if st == "unsupported":
        return (f"formal cannot translate {what}: {w.get('detail', '')}. Use only labelled "
                f"`cover property (@(posedge clk) [disable iff (rst)] expr);` and clocked tracking registers.")
    if st == "invalid":
        return f"formal rejected {what}: {w.get('detail', '')}"
    return f"cover_witness returned status {st!r} for {what} without a witness"


def formal(item: PlanItem, w: dict | None, twin: dict | None = None, *, assumptions: str = "",
           bound: int | None = None, min_frames: float | None = None, frame_cycles: str | None = None,
           twin_violations: list[str] = ()) -> GateResult:
    """w: the target's witness, None if the candidate has its own (checking) gold.
    twin: the twin cover's witness, None if there is no twin.
    min_frames: reject a target witness shorter than this many frames (hardening);
    needs frame_cycles, the pack's frame length expression (formal.yaml).
    """
    if min_frames is not None and not frame_cycles:
        raise FormalError("min_frames needs frame_cycles in the pack's formal/formal.yaml")
    data = {"gold_source": "llm" if w is None else "formal", "bound": bound, "min_frames": min_frames,
            "assumptions": assumptions}
    where = f"(bound {bound} cycles, formal environment in {assumptions})"
    msgs = []
    if w is not None:
        data |= _summary(w, frame_cycles)
        if why := _not_found(f"the target cover {item.cover}", w, where):
            return GateResult("formal", False, why, data)
        frames = data.get("witness_frames")
        if min_frames is not None and frames < min_frames:
            return GateResult("formal", False, f"witness is {frames:.2f} frames, below {min_frames:g}: make the "
                                               f"target need more protocol activity (a further phase or an "
                                               f"interaction), not more waiting or a slower prescale", data)
        msgs.append(f"witness depth {w['depth']} cycles" + (f" ({frames:.2f} frames)" if frames is not None else "")
                    + f", {w['input_changes']} input changes {where}")
    if twin_violations:
        return GateResult("formal", False, "twin.sv: policy: " + "\n".join(twin_violations), data)
    if twin is not None:
        data["twin"] = _summary(twin, frame_cycles)
        if why := _not_found("the twin cover", twin, where):
            if twin["status"] == "unreachable":
                why = (f"the twin cover is unreachable {where}: boundary not exact. The twin must be the "
                       f"reachable off-by-one condition next to the target.")
            return GateResult("formal", False, why, data)
        msgs.append(f"twin witness depth {twin['depth']}")
    return GateResult("formal", True if msgs else "n/a", "; ".join(msgs) or "the candidate has its own gold", data)


def reach_gold_text(w: dict, bound: int) -> str:
    """A reach gold: the witness testbench under a header naming its source and depth."""
    return (f"{REACH_HEADER}\n// closure_core.formal.cover_witness: depth {w['depth']}, input_changes "
            f"{w['input_changes']}, bound {bound}, witness {w['key'][:16]}\n{w['tb_text']}")


def twin_near_miss_text(w: dict, bound: int) -> str:
    return (f"// near_miss_source: formal witness of the twin cover; depth {w['depth']}, bound {bound}, "
            f"witness {w['key'][:16]}\n{w['tb_text']}")


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


def composed_testbenches(design: Design, item: PlanItem) -> dict[str, Path]:
    """Testbenches a composed item may inherit as near-misses: every component's gold
    (gold:<C>) and near-misses (near_miss:<file>). composed_near_misses picks among them."""
    out = {f"gold:{c}": design.golds[c] for c in item.composed_from if c in design.golds}
    out |= {f"near_miss:{q.name}": q for c in item.composed_from for q in design.near_misses.get(c, ())}
    return out


def composed_near_misses(item: PlanItem, sims: dict[str, Simulation]) -> list[tuple[str, Simulation]]:
    """The inherited near-misses of a composed item, each of which must miss the composite.

    Component near-misses always. Component golds by template: cross, seq and
    count take every component's gold (each reaches a part, not the
    combination); excl(A, B) takes A's gold only if it also hits B (then "A
    without B" must not hold); budget takes none (A's gold may well be within
    the budget).
    """
    t, comps = item.template, item.composed_from
    golds = []
    if t in ("cross", "seq", "count"):
        golds = [f"gold:{c}" for c in comps]
    elif t == "excl" and len(comps) == 2:
        golds = [f"gold:{comps[0]}"] if (g := sims.get(f"gold:{comps[0]}")) and g.plan_hits.get(comps[1], 0) > 0 \
            else []
    names = golds + sorted(n for n in sims if n.startswith("near_miss:"))
    return [(n, sims[n]) for n in names if n in sims]


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


def _requirements(verified: list[tuple[dict, bool | None]]) -> list[dict]:
    return [s for s, ok in verified
            if s.get("role") == "requirement" and s["type"] in REQUIREMENT_TYPES and ok is True]


def value(kills: list[str], only: list[str], verified: list[tuple[dict, bool | None]],
          inherited: dict[str, list[tuple[dict, bool | None]]] | None = None) -> GateResult:
    """verified: (source, citation verified) per plan source. Only verified DOC or
    README sources with role: requirement count; RTL and BASE say what the
    design does, not what it must do.

    inherited: for a composed item, component ID -> its (source, verified); the
    components' verified requirements count as this item's spec evidence.
    """
    reqs = _requirements(verified)
    inh = {c: _requirements(v) for c, v in (inherited or {}).items()}
    spec = [source_label(s) for s in reqs] + [f"{source_label(s)} (from {c})" for c, rs in inh.items() for s in rs]
    evidence = {(True, True): "both", (True, False): "mutant",
                (False, True): "spec", (False, False): "none"}[(bool(kills), bool(spec))]
    return GateResult(
        "value", evidence != "none",
        f"evidence {evidence}; kills {len(kills)} baseline survivors"
        + (f" ({len(only)} only by this gold: {', '.join(only)})" if only else "")
        + f"; requirements: {'; '.join(spec) or '-'}",
        {"evidence": evidence, "kills": kills, "only_by_this_gold": only, "requirements": spec,
         "requirement_keys": [requirement_key(s) for s in reqs],
         **({"inherited_from": sorted(c for c, rs in inh.items() if rs)} if inherited else {})})


def inherited_requirements(design: Design, item: PlanItem, store: cit.DocStore,
                           base_points: list) -> dict[str, list] | None:
    """For a composed item: component ID -> its (source, verified), for value(inherited=...)."""
    if not item.composed_from:
        return None
    return {c: citations(design, design.item(c), store, base_points).data["verified"] for c in item.composed_from}


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
    """Atomic: parallel gate runs (tools/propose_plan -p) share this file, and a torn
    read would crash a run. Writers of a shared cache merge (merge_cache). The temp
    name is unique per call: every container is PID 1, so a pid suffix collides."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(dict(cache), indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


_CACHE_THREADS = threading.Lock()  # lockf excludes other processes only, not this one's threads


@contextmanager
def cache_lock(path: Path):
    """Exclusive lock for writing the shared cache `path` (a file or a directory), held
    on <path>.lock with lockf, as in formal_slot, so it excludes other containers too."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_THREADS, open(path.parent / f"{path.name}.lock", "a+") as f:
        fcntl.lockf(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.lockf(f, fcntl.LOCK_UN)


def merge_cache(path: Path, entries: dict) -> int:
    """Add the entries the cache file does not have yet, under cache_lock: runs and
    worktrees share it, and an existing entry is never overwritten. Returns how many
    were added."""
    entries = dict(entries)  # one copy: simulation threads may be adding to it
    with cache_lock(path):
        ours = json.loads(path.read_text()) if path.exists() else {}
        new = {k: v for k, v in entries.items() if k not in ours}
        if new:
            save_cache(path, {**ours, **new})
        return len(new)


def mutation_runs(design: Design, golds: dict[str, Path], pool, cache_path: Path) -> dict:
    """Run the mutants against the baselines, then the golds against the survivors.

    Not a gate: the kills are evidence for the value gate and feed the survivor
    bookkeeping. Only checking golds run: a reach gold (formal witness) has no
    checks, so a mutant it "kills" would only show a changed path, not a
    caught bug. Every testbench runs only against mutants of modules it
    instantiates. Golds skip mutants a baseline already kills: every output
    here is computed from survivors or from baseline kills.
    """
    golds = {i: p for i, p in golds.items() if gold_source(p) != "formal"}  # reach golds check nothing
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    ms = [m for f, (lo, hi) in design.mutate.items() for m in mutants.generate(f, lo, hi)]
    tbs = {f"baseline:{n}": (b["file"].read_text(), b["top"]) for n, b in design.baselines.items()}
    tbs.update({f"gold:{i}": (p.read_text(), "tb") for i, p in golds.items()})

    run = lambda tb, m=None: pool.submit(mutants.simulate, design, *tbs[tb], m, cache=cache)
    orig = {tb: f.result() for tb, f in {tb: run(tb) for tb in tbs}.items()}
    save = lambda: merge_cache(cache_path, cache)
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
