"""Plan proposer: a model proposes candidate plan items; mechanical gates decide.

Generation is recorded, judgment is reproducible. Everything the model received
and returned is saved under runs/propose/<run_id>/; `replay` re-runs every gate
on the recorded responses with no model calls and must reproduce the same
accept/reject decisions, repair messages and summary.

  Stage A   one call lists candidates (tasks, and waiver proposals that are
            recorded but never accepted)
  Stage B   one conversation per task candidate writes the bundle; on a gate
            failure the conversation continues with the structured failure,
            at most RETRIES times. With target_only the model writes only the
            plan entry, the cover and an optional twin cover; formal finds the
            gold (gates.formal), and its witnesses are recorded under formal/
  Seed      (optional) every task candidate of an earlier run, its latest bundle
            as attempt 0 without a model call; Stage A is told to list others
  Set       individually accepted candidates are gated again in order against
            a cumulative pack, so two duplicates from the same run cannot
            both be accepted
  Write     (optional) accepted items get final IDs and provenance, go into the
            real pack, and the full validity suite runs

The model loop runs on the host; every simulation runs through an Executor,
by default the toolchain image with networking off, because model-written
SystemVerilog is simulated there.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from closure_core.design import Design, find_repo_root, load_design
from closure_core.infra import InfraError, default_jobs

ROOT = find_repo_root()
PROMPTS = Path(__file__).with_name("prompts")
PRIME_BASE_URL = "https://api.pinference.ai/api/v1"
# Pipeline image (tag formal): Verilator 5.020 plus the formal tools in /opt/oss-cad-suite.
# The agent and grading sandboxes use the Verilator-only image (taskset DEFAULT_IMAGE):
# a bash agent with SymbiYosys could get a witness from a model checker.
# tests/test_images.py keeps the two apart and checks Verilator is the same in both.
IMAGE = ("docker.io/vishokjcs/closure-bench-toolchain@"
         "sha256:89f72e65e6a136f18f7187eeac78ec8a43d4ea51ebddbec0b2ce2dae5c11f5fa")
RETRIES = 2
# --target-only default for --min-frames. Calibrated on the formal witnesses of the 13
# reachable plan items and the 3 targets of a min-depth-160 smoke run (2026-10-26):
# two-frame targets measure 1.950-1.966 frames, one-frame ones 1.000-1.050, single
# events below 0.09; a transmitter target with two real frames (prescale 1, then 3,
# covered before the second stop bit) measured 1.85 and was rejected at 1.9. 1.5 lies
# between one frame (<= 1.05) and two (>= 1.85): it accepts two frames and rejects one.
TARGET_MIN_FRAMES = 1.5

GATES = ["format", "cover_sync", "cover_policy", "description_sync", "mechanism", "citations", "formal", "baseline",
         "gold", "near_miss", "determinism", "value", "duplicate"]
PREFIX = {"uart_rx": "R", "uart_tx": "T"}  # bind target -> ID prefix; anything else is M


def sha256(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")


def load(path: Path):
    return json.loads(path.read_text())


# --- context pack (built in the image: needs Verilator and pypdf) --------------------------

def build_context_pack(design: Design, *, full_docs: bool = False, cache_path: Path | None = None,
                       j: int = 8, progress: bool = True) -> dict:
    """What the model is shown, as data. progress: also the existing plan's progress
    (progress_before: a mutation sweep and every gold; not shown to the model). A
    target-only run leaves it out to start in seconds; finish() computes it then."""
    from concurrent.futures import ThreadPoolExecutor

    from closure_core import citations, gates, sim
    from closure_core.infra import simulate

    # Shown to the model as repo paths, also when the pack is a run's base_pack snapshot.
    def rel(p) -> str:
        p = Path(p)
        if p.is_relative_to(design.pack):
            return f"designs/{design.name}/{p.relative_to(design.pack)}"
        return str(p.relative_to(design.repo_root))

    with ThreadPoolExecutor(j) as pool:
        sims = {n: f.result() for n, f in {n: pool.submit(simulate, design, b["file"].read_text(), top=b["top"])
                                           for n, b in design.baselines.items()}.items()}
    hits: dict[tuple, int] = {}
    for s in sims.values():
        for p in s.points:
            if p.kind in ("v_line", "v_branch", "v_toggle") and "/rtl/" in p.file:
                k = (p.kind, Path(p.file).name, p.line, p.name)
                hits[k] = max(hits.get(k, 0), p.hits)
    holes = [dict(zip(("kind", "file", "line", "name"), k)) for k, h in sorted(hits.items()) if h == 0]

    registry = yaml.safe_load((design.pack / "sources.yaml").read_text())["documents"]
    store = citations.DocStore(design.pack, offline=True)
    docs = {}
    for doc, meta in registry.items():
        pages = store.pages(doc)
        chosen = ([{"page": n, "reason": "full document"} for n in range(1, len(pages) + 1)]
                  if full_docs else meta.get("context_pages", []))
        docs[doc] = {"title": meta["title"],
                     "pages": [{**c, "text": pages[c["page"] - 1]} for c in chosen]}
    readme = design.repo_root / "third_party/verilog-uart/README.md"
    pack = {
        "design": design.name,
        "toolchain": sim.verilator_version(),
        "verilator_flags": list(sim.VERILATOR_FLAGS),
        "rtl": {rel(p): p.read_text() for p in design.rtl},
        "readme": {rel(readme): readme.read_text()},
        "baselines": {rel(b["file"]): b["file"].read_text() for b in design.baselines.values()},
        "baseline_status": {n: s.sim.status for n, s in sims.items()},
        "holes": holes,
        "plan": [{"id": it.id, "description": it.description, "cover": it.cover} for it in design.plan],
        "covers": {rel(c): c.read_text() for c in design.covers},
        "waivers": (design.pack / "waivers.yaml").read_text() if (design.pack / "waivers.yaml").exists() else "",
        "docs": docs,
        "full_docs": full_docs,
        # Shown only in target-only mode: the formal environment (what formal may assume).
        "formal": {f"designs/{design.name}/{gates.FORMAL_DIR}/{n}": t for n, t in gates.formal_files(design).items()},
    }
    if progress:
        pack["progress_before"] = progress_before(design, sims, cache_path=cache_path, j=j)
    return pack


def progress_before(design: Design, sims: dict | None = None, *, cache_path: Path | None = None,
                    j: int = 8) -> dict:
    """Not shown to the model: what the existing plan already achieves, so the
    summary can report what a run adds (see summarize, "progress"). sims: the
    baseline simulations, if already run."""
    from concurrent.futures import ThreadPoolExecutor

    from closure_core import gates, mutants
    from closure_core.infra import simulate
    with ThreadPoolExecutor(j) as pool:
        if sims is None:
            sims = {n: f.result() for n, f in {n: pool.submit(simulate, design, b["file"].read_text(), top=b["top"])
                                               for n, b in design.baselines.items()}.items()}
        mutation = gates.mutation_runs(design, design.golds, pool, cache_path or gates.MUTATION_CACHE)
        gold_sims = {i: f.result() for i, f in {i: pool.submit(simulate, design, p.read_text())
                                                 for i, p in design.golds.items()}.items()}
    hole_keys = gates.holes(sims)
    survivors = sorted(mutation["unexplained"] + mutation["survivors_killed_by_gold"])
    by_id = {m.id: m for f, (lo, hi) in design.mutate.items() for m in mutants.generate(f, lo, hi)}
    return {
        "survivors": survivors,
        "survivor_details": {i: {"file": by_id[i].file, "line": by_id[i].line, "op": by_id[i].op,
                                 "original": by_id[i].original.strip(), "mutated": by_id[i].mutated.strip()}
                             for i in survivors},
        "killed_by_plan": mutation["survivors_killed_by_gold"],
        "holes": hole_keys,
        "waived_holes": sorted(k for k in gates.waived_holes(design) if k in hole_keys),
        "closed_by_plan": sorted({k for s in gold_sims.values() if s.sim.status == "ok"
                                  for k in gates.hit_points(s)} & set(hole_keys)),
        "requirements_by_plan": sorted({gates.requirement_key(s) for it in design.plan for s in it.sources
                                        if s.get("role") == "requirement"
                                        and s["type"] in gates.REQUIREMENT_TYPES}),
    }


def _numbered(text: str) -> str:
    return "\n".join(f"{n:4}| {line}" for n, line in enumerate(text.splitlines(), 1))


def render_context(pack: dict, rules: str, target_only: bool = False) -> str:
    out = [rules, "## Repository (line numbers are for citations)"]
    for path, text in {**pack["rtl"], **pack["readme"]}.items():
        out.append(f"### {path}\n```\n{_numbered(text)}\n```")
    out.append("## Baseline testbenches")
    out += [f"### {path}\n```systemverilog\n{text}\n```" for path, text in pack["baselines"].items()]
    out.append("## Baseline coverage holes (0 hits; cite as BASE points)\n"
               + "\n".join(f"- {{kind: {h['kind']}, file: {h['file']}, line: {h['line']}, name: {h['name']}}}"
                           for h in pack["holes"]))
    out.append("## How testbenches are compiled\n`verilator " + " ".join(pack["verilator_flags"])
               + " --top-module tb ...` with every RTL and cover file.")
    out.append("## Existing plan items (do not repeat)\n"
               + "\n".join(f"- {p['id']} ({p['cover']}): {p['description']}" for p in pack["plan"]))
    out += [f"### {path}\n```systemverilog\n{text}\n```" for path, text in pack["covers"].items()]
    out.append(f"## Waivers (mutants judged equivalent)\n```yaml\n{pack['waivers']}\n```")
    out.append("## Documents (extracted page text; cite as DOC with doc id and page)")
    for doc, d in pack["docs"].items():
        for p in d["pages"]:
            out.append(f"### {doc}, page {p['page']} ({d['title']}; included: {p['reason']})\n"
                       f"```text\n{p['text']}\n```")
    if target_only:
        out.append("## Formal environment (the input assumptions formal searches under)")
        out += [f"### {path}\n```{'yaml' if path.endswith('.yaml') else 'systemverilog'}\n{text}\n```"
                for path, text in pack.get("formal", {}).items()] or ["(none)"]
    return "\n\n".join(out)


def prompt_files() -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(PROMPTS.glob("*.md"))}


def prompt_sha() -> str:
    return sha256(json.dumps(prompt_files(), sort_keys=True))


def fill(template: str, **fields: str) -> str:
    for k, v in fields.items():  # not str.format: SystemVerilog and YAML are full of braces
        template = template.replace("{" + k + "}", v)
    return template


# --- parsing --------------------------------------------------------------------------------

class ParseError(ValueError):
    pass


def _blocks(text: str, tag: str) -> list[tuple[dict, str]]:
    out = []
    for m in re.finditer(rf"<{tag}((?:\s+\w+=\"[^\"]*\")*)\s*>(.*?)</{tag}>", text, re.S):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        out.append((attrs, m.group(2).strip("\n")))
    return out


def parse_candidates(text: str) -> list[dict]:
    blocks = _blocks(text, "candidates")
    if len(blocks) != 1:
        raise ParseError(f"expected one <candidates> block, found {len(blocks)}")
    try:
        cands = yaml.safe_load(blocks[0][1])
    except yaml.YAMLError as e:
        raise ParseError(f"<candidates> is not valid YAML: {e}") from None
    if not isinstance(cands, list) or not all(isinstance(c, dict) for c in cands):
        raise ParseError("<candidates> must be a YAML list of mappings")
    return cands


def parse_target_candidates(text: str) -> list[dict]:
    """Target-only Stage A: every task names at least MIN_MECHANISMS distinct mechanisms."""
    from closure_core.gates import MECHANISMS, MIN_MECHANISMS, declared_mechanisms

    def valid(c: dict) -> bool:
        ms = declared_mechanisms(c)
        return len(set(ms)) == len(ms) >= MIN_MECHANISMS and set(ms) <= set(MECHANISMS)

    cands = parse_candidates(text)
    bad = [str(c.get("title")) for c in cands if c.get("kind") == "task" and not valid(c)]
    if bad:
        raise ParseError(f"tasks without a valid mechanism list (at least {MIN_MECHANISMS} distinct of "
                         f"{', '.join(MECHANISMS)}): {bad}")
    return cands


def parse_survivor_answer(text: str, survivors: list[str]) -> tuple[list[dict], list[dict]]:
    """Pass 2: (candidates, unkillable). Every survivor must be addressed exactly once."""
    cands = parse_candidates(text)
    blocks = _blocks(text, "unkillable")
    if len(blocks) != 1:
        raise ParseError(f"expected one <unkillable> block, found {len(blocks)}")
    try:
        unk = yaml.safe_load(blocks[0][1]) or []
    except yaml.YAMLError as e:
        raise ParseError(f"<unkillable> is not valid YAML: {e}") from None
    if not isinstance(unk, list) or not all(isinstance(u, dict) and {"mutant", "reason"} <= set(u) for u in unk):
        raise ParseError("<unkillable> must be a YAML list of {mutant, reason}")
    named = [str(m) for c in cands for m in (c.get("targets") or [])] + [str(u["mutant"]) for u in unk]
    unknown = sorted(set(named) - set(survivors))
    targeted = {str(m) for c in cands for m in (c.get("targets") or [])}
    twice = sorted({str(u["mutant"]) for u in unk if str(u["mutant"]) in targeted})
    missing = sorted(set(survivors) - set(named))
    errs = ([f"not remaining survivors: {unknown}"] if unknown else []) + \
           ([f"both targeted and called unkillable: {twice}"] if twice else []) + \
           ([f"survivors not addressed: {missing}"] if missing else []) + \
           ([f"{c.get('title')!r} is a task with no targets" for c in cands
             if c.get("kind") == "task" and not c.get("targets")])
    if errs:
        raise ParseError("; ".join(errs))
    return cands, unk


def parse_bundle(text: str, target_only: bool = False) -> dict:
    """target_only: plan, cover and an optional twin; formal writes the gold."""
    found = {t: _blocks(text, t) for t in ("plan", "cover", "gold", "near_miss", "twin")}
    missing = [t for t in ("plan", "cover") + (() if target_only else ("gold",)) if len(found[t]) != 1]
    if missing:
        raise ParseError("expected exactly one block each of " + ", ".join(f"<{t}>" for t in missing))
    if target_only and (found["gold"] or found["near_miss"]):
        raise ParseError("write no <gold> or <near_miss> blocks: formal finds the gold, and the twin's "
                         "witness is the near-miss")
    if len(found["twin"]) > 1:
        raise ParseError("at most one <twin> block")
    fallback = False
    try:
        plan = yaml.safe_load(found["plan"][0][1])
    except yaml.YAMLError as e:
        # The usual cause is a colon in a plain description; quoting it is the only fix tried.
        quoted = _quote_description(found["plan"][0][1])
        try:
            if quoted is None:
                raise e
            plan, fallback = yaml.safe_load(quoted), True
        except yaml.YAMLError:
            raise ParseError(f"<plan> is not valid YAML: {e}") from None
    if not isinstance(plan, dict):
        raise ParseError("<plan> must be a YAML mapping")
    near = {}
    for attrs, body in found["near_miss"]:
        name = attrs.get("name", "")
        if not re.fullmatch(r"[a-z0-9_]+", name) or name in near:
            raise ParseError(f"near_miss name {name!r} must be unique lowercase [a-z0-9_]")
        near[name] = body
    one = lambda t: found[t][0][1] + "\n" if found[t] else None
    return {"plan": plan, "cover": one("cover"), "gold": one("gold"), "twin": one("twin"),
            "near_miss": {n: b + "\n" for n, b in near.items()}, "yaml_fallback": fallback}


def _quote_description(text: str) -> str | None:
    """The <plan> text with only a plain (unquoted, not block) description value
    double-quoted, its continuation lines folded in; None if there is none."""
    lines = text.split("\n")
    for n, line in enumerate(lines):
        m = re.match(r"([ \t]*)description:[ \t]+(\S.*)$", line)
        if not m or m.group(2)[0] in "\"'>|":
            continue
        end = n + 1  # a plain scalar continues on more-indented lines
        while end < len(lines) and lines[end].strip() and len(lines[end]) - len(lines[end].lstrip()) > len(m.group(1)):
            end += 1
        value = " ".join(x.strip() for x in [m.group(2), *lines[n + 1:end]])
        return "\n".join([*lines[:n], f"{m.group(1)}description: {json.dumps(value)}", *lines[end:]])
    return None


def substitute(text: str, old: str, new: str) -> str:
    """Replace the ID token: cov_ITEM, u_cov_ITEM and ITEM_x all match; ITEMS and P10 do not."""
    return re.sub(rf"(?<![A-Za-z0-9]){re.escape(old)}(?![A-Za-z0-9])", new, text)


def write_candidate(bundle: dict, item_id: str, dest: Path, token: str = "ITEM") -> None:
    """Candidate directory for tools/gate_candidate, with token replaced by item_id."""
    plan = yaml.safe_load(substitute(yaml.safe_dump(bundle["plan"], sort_keys=False), token, item_id))
    plan = {"id": item_id, **{k: v for k, v in plan.items() if k != "id"}, "cover_module": f"cov_{item_id}"}
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "item.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
    (dest / "cover.sv").write_text(substitute(bundle["cover"], token, item_id))
    for key in ("gold", "twin"):
        if bundle.get(key) is not None:
            (dest / f"{key}.sv").write_text(substitute(bundle[key], token, item_id))
    for name, body in bundle["near_miss"].items():
        (dest / "near_miss").mkdir(exist_ok=True)
        (dest / "near_miss" / f"{name}.sv").write_text(substitute(body, token, item_id))


def format_failure(detail: str) -> dict:
    """A gate result for a response that could not be parsed into a bundle."""
    return {"item": None, "accepted": False, "failed_gate": "format",
            "gates": [{"gate": "format", "ok": False, "detail": detail, "data": {}}],
            "skipped": GATES[1:]}


def repair_message(res: dict) -> str:
    g = next(x for x in res["gates"] if x["gate"] == res["failed_gate"])
    detail = (g["detail"] or "")[-3000:]  # compile/run log tails are already in the detail
    return fill((PROMPTS / "repair.md").read_text(), gate=g["gate"], detail=detail)


# --- model ----------------------------------------------------------------------------------

class PrimeModel:
    """Prime Inference, OpenAI-compatible; bills the PRIME_API_KEY owner."""

    def __init__(self, model: str, temperature: float, max_tokens: int):
        from openai import OpenAI  # optional dependency: --extra propose
        self.client = OpenAI(base_url=PRIME_BASE_URL, api_key=os.environ["PRIME_API_KEY"])
        self.params = {"model": model, "temperature": temperature, "max_tokens": max_tokens}

    def __call__(self, messages: list[dict]) -> dict:
        t = time.time()
        r = self.client.chat.completions.create(messages=messages, **self.params)
        return {"text": r.choices[0].message.content or "", "finish_reason": r.choices[0].finish_reason,
                "id": r.id, "model": r.model, "usage": r.usage.model_dump() if r.usage else None,
                "seconds": round(time.time() - t, 1)}


class ScriptedModel:
    """Returns canned responses in order (tests); a callable gets the messages."""

    def __init__(self, texts: list, model: str = "scripted"):
        self.texts, self.params = list(texts), {"model": model, "temperature": 0, "max_tokens": 0}

    def __call__(self, messages: list[dict]) -> dict:
        t = self.texts.pop(0)
        return {"text": t(messages) if callable(t) else t, "finish_reason": "stop", "id": "scripted", "model": "scripted",
                "usage": None, "seconds": 0}


# --- executor -------------------------------------------------------------------------------

class Executor:
    """Runs repo tools in the toolchain image (networking off) or, with image=None, locally."""

    def __init__(self, image: str | None = IMAGE, j: int | None = None):
        self.image, self.j = image, j or default_jobs()

    @property
    def label(self) -> str:
        """Recorded in the manifest, per run and per gated candidate."""
        return f"docker:{self.image}" if self.image else "local"

    def run(self, argv: list[str]) -> subprocess.CompletedProcess:
        if self.image:
            cache = Path.home() / ".cache" / "closure-bench"
            argv = ["docker", "run", "--rm", "--network", "none", "-v", f"{ROOT}:/repo", "-w", "/repo",
                    "-v", f"{cache}:/root/.cache/closure-bench", self.image, *argv]
        return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)

    def gate(self, cand: Path, out: Path, base: Path | None = None, formal: dict | None = None) -> dict:
        """formal: formal_opts(...), the run's witness cache and minimum frames."""
        argv = ["tools/gate_candidate", _rel(cand), "--out", _rel(out), "-j", str(self.j)]
        if base:
            argv += ["--base", _rel(base)]
        if formal:
            argv += ["--witness-cache", _rel(formal["cache"])]
            argv += ["--require-mechanism"] if formal.get("require_mechanism") else []
            argv += ["--min-frames", str(formal["min_frames"])] if formal.get("min_frames") is not None else []
        p = self.run(argv)
        if p.returncode == 2 and not out.exists():  # the machine failed, not the candidate
            raise InfraError(p.stderr.strip()[-2000:])
        if not out.exists():
            raise RuntimeError(f"gate_candidate failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
        return load(out)

    def context_pack(self, out: Path, full_docs: bool, base: Path, progress: bool = True) -> dict:
        p = self.run(["tools/context_pack", "--out", _rel(out), "--design", _rel(base), "-j", str(self.j),
                      *(["--full-docs"] if full_docs else []), *([] if progress else ["--no-progress"])])
        if p.returncode != 0:
            raise RuntimeError(f"context_pack failed:\n{p.stderr[-2000:]}")
        return load(out)

    def progress_before(self, out: Path, base: Path) -> dict:
        p = self.run(["tools/context_pack", "--out", _rel(out), "--design", _rel(base), "-j", str(self.j),
                      "--progress-only"])
        if p.returncode != 0:
            raise RuntimeError(f"context_pack --progress-only failed:\n{p.stderr[-2000:]}")
        return load(out)

    def check(self) -> dict:
        p = self.run(["tools/check", "-j", str(self.j)])
        return {"exit": p.returncode, "tail": p.stdout[-3000:]}


def _rel(p: Path) -> str:
    return str(p.resolve().relative_to(ROOT))


# --- run ------------------------------------------------------------------------------------

def _git() -> dict:
    if not shutil.which("git"):  # e.g. tests inside the toolchain image
        return {"commit": None, "dirty": None}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                                text=True).stdout.strip())
    return {"commit": head, "dirty": dirty}


def new_run_dir(tag: str = "") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "runs" / "propose" / (stamp + (f"-{tag}" if tag else ""))


def _call(model, messages: list[dict], path: Path) -> str:
    if path.exists():  # resume: the recorded response, if it answered these exact messages
        rec = load(path)
        if rec["messages"] != messages:
            raise RuntimeError(f"{path}: recorded messages differ from the ones this code sends; cannot resume")
        return rec["response"]["text"]
    resp = model(messages)
    dump(path, {"messages": messages, "params": model.params, "response": resp})
    return resp["text"]


def stage_a(run_dir: Path, model, prompt: str, tag: str, parse) -> tuple[object | None, str | None]:
    """One Stage A conversation (tag stage_a or stage_a2) with at most RETRIES repair turns.

    parse(text) raises ParseError; the strict parser is the only one used. Returns
    (parsed, None) or (None, the last parse error).
    """
    messages = [{"role": "user", "content": prompt}]
    for attempt in range(RETRIES + 1):
        text = _call(model, messages, run_dir / "responses" / tag / f"{attempt}.json")
        try:
            return parse(text), None
        except ParseError as e:
            err = str(e)
        messages = [*messages, {"role": "assistant", "content": text},
                    {"role": "user", "content": stage_a_repair(err)}]
    return None, err


def stage_a_repair(error: str) -> str:
    return fill((PROMPTS / "repair_stage_a.md").read_text(), error=error[-3000:])


def _number(cands: list[dict], start: int, pass_no: int) -> list[dict]:
    for n, c in enumerate(cands, start):
        c["cid"], c["pass"] = f"c{n:02d}", pass_no
    return cands


def _before(run_dir: Path) -> dict:
    """The existing plan's progress: from the context pack, or measured by finish()."""
    pack = load(run_dir / "context_pack.json")
    return pack["progress_before"] if "progress_before" in pack else load(run_dir / "progress_before.json")


def survivor_prompt(run_dir: Path, context: str) -> tuple[str, list[str]]:
    """Pass 2 prompt from pass 1's set stage, and the survivors it lists."""
    before = _before(run_dir)
    cands = load(run_dir / "candidates.json")["candidates"]
    acc = {c["cid"]: _final_attempt(run_dir, c["cid"])[1] for c in cands
           if c["pass"] == 1 and (s := run_dir / "set" / f"{c['cid']}.json").exists() and load(s)["accepted"]}
    remaining = remaining_survivors(before, acc)
    lines = []
    for c in cands:
        if c["cid"] in acc:
            att = _final_attempt(run_dir, c["cid"])[0]
            item = yaml.safe_load((run_dir / "candidates" / c["cid"] / str(att) / "item.yaml").read_text())
            lines.append(f"- {c['title']}: {item['description']}")
    det = before["survivor_details"]
    surv = "\n".join(f"- {m}  ({det[m]['file']}:{det[m]['line']}, {det[m]['op']})\n"
                     f"    original: {det[m]['original']}\n    mutated:  {det[m]['mutated']}" for m in remaining)
    return fill((PROMPTS / "survivors.md").read_text(), context=context,
                accepted="\n".join(lines) or "(none)", survivors=surv or "(none)"), remaining


def run(run_dir: Path, model, executor: Executor, *, design_name: str = "uart",
        max_candidates: int = 20, stage_a_only: bool = False, full_docs: bool = False,
        write: bool = False, base: Path | None = None, survivor_pass: bool = False,
        parallel: int = 1, target_only: bool = False, min_frames: float | None = None,
        seed_from: Path | None = None) -> dict:
    """base: the pack to gate against (default designs/<design_name>; tests pass another).

    survivor_pass: after pass 1 and its set stage, a second Stage A sees the
    remaining baseline survivors and must address each one (pass 2).
    parallel: Stage B conversations at a time (model calls dominate the run time).
    target_only: Stage B writes no gold (prompts/author_target.md); formal finds it.
    The survivor pass is off in this mode: a reach gold kills no mutant.
    min_frames: the formal gate's minimum target witness length in frames (bound,
    timeout and the frame length come from the pack's formal/formal.yaml).
    seed_from: an earlier target-only run, copied into seed/<its id>; its task
    candidates are seeded (seed_candidates).
    """
    survivor_pass = survivor_pass and not target_only
    if seed_from and not (target_only and load(seed_from / "manifest.json").get("target_only")):
        raise ValueError("--seed-from needs --target-only, and a target-only run to seed from")
    run_dir.mkdir(parents=True)
    seed = None
    if seed_from:  # a copy, so the run and its replay never read the source again
        seed = f"{SEED_DIR}/{seed_from.name}"
        shutil.copytree(seed_from, run_dir / seed, ignore=shutil.ignore_patterns("replay", "setpack"))
    # Every gate in this run, and in its replay, uses this snapshot of the pack.
    shutil.copytree(base or ROOT / "designs" / design_name, run_dir / "base_pack")
    # Target-only: no mutation sweep at startup (no survivor pass to show it to); finish() measures it.
    pack = executor.context_pack(run_dir / "context_pack.json", full_docs, run_dir / "base_pack",
                                 progress=not target_only)
    rules = (PROMPTS / "rules.md").read_text()
    context = render_context(pack, rules, target_only)
    dump(run_dir / "manifest.json", {
        "run_id": run_dir.name, "git": _git(), "image": executor.image or "local", "executor": executor.label,
        "toolchain": pack["toolchain"], "model": model.params, "retries": RETRIES,
        "prompt_sha": prompt_sha(), "context_pack_sha": sha256((run_dir / "context_pack.json").read_text()),
        "full_docs": full_docs, "max_candidates": max_candidates, "stage_a_only": stage_a_only,
        "write": write, "design": design_name, "survivor_pass": survivor_pass, "parallel": parallel,
        "target_only": target_only, "min_frames": min_frames,
        **({"seed": seed, "seed_from": str(seed_from.resolve())} if seed else {})})
    (run_dir / "prompts").mkdir()
    for name, text in prompt_files().items():
        (run_dir / "prompts" / name).write_text(text)
    return _flow(run_dir, model, executor, context)


def resume(run_dir: Path, model, executor: Executor, parallel: int = 1) -> dict:
    """Continue an interrupted run in place.

    Re-runs the run's flow: every model call, gate and set result already
    recorded is reused (a recorded model call only if this code sends the same
    messages), so only the missing steps run. A finished run can be resumed
    only to retry its infrastructure aborts (infra/). --replay afterwards checks the
    whole run as for one that was never interrupted.
    """
    manifest = load(run_dir / "manifest.json")
    aborted = sorted(p.stem for p in (run_dir / "infra").glob("*.json"))
    if (run_dir / "summary.json").exists() and not aborted:
        raise RuntimeError("the run finished (summary.json exists); nothing to resume")
    if manifest["prompt_sha"] != prompt_sha():
        raise RuntimeError("the prompt templates changed since the run started; cannot resume")
    manifest.setdefault("resumed", []).append({"git": _git(), "parallel": parallel, "retried_infra": aborted,
                                               "executor": executor.label})
    shutil.rmtree(run_dir / "infra", ignore_errors=True)  # an abort is written again if it recurs
    (run_dir / "summary.json").unlink(missing_ok=True)
    manifest["parallel"] = parallel
    dump(run_dir / "manifest.json", manifest)
    context = render_context(load(run_dir / "context_pack.json"), (PROMPTS / "rules.md").read_text(),
                             manifest.get("target_only", False))
    return _flow(run_dir, model, executor, context)


def enumerate_prompt(context: str, target_only: bool = False, n: int = 20, seeded: list[dict] = ()) -> str:
    """target_only: also the mechanism rules and a request for exactly n targets.
    seeded: candidates seeded from an earlier run, listed so the model proposes others."""
    prompt = fill((PROMPTS / "enumerate.md").read_text(), context=context)
    if target_only:
        prompt += "\n" + fill((PROMPTS / "enumerate_target.md").read_text(), n=str(n))
    if seeded:
        listed = "\n".join(f"- {c.get('title')}: {' '.join(str(c.get('behaviour', '')).split())}" for c in seeded)
        prompt += "\n" + fill((PROMPTS / "seeded.md").read_text(), seeded=listed)
    return prompt


def first_candidates(cands: list[dict], n: int, target_only: bool) -> list[dict]:
    """Pass 1's candidates, at most n. Target-only: the first n tasks and every waiver
    proposal, in order (the prompt asks for n targets; waivers are only recorded)."""
    if not target_only:
        return cands[:n]
    keep = set([i for i, c in enumerate(cands) if c.get("kind") == "task"][:n])
    return [c for i, c in enumerate(cands) if c.get("kind") != "task" or i in keep]


def formal_opts(run_dir: Path, manifest: dict) -> dict:
    """The formal gate's settings for a run: its own witness cache, minimum frames, and
    (target-only) the required difficulty mechanisms."""
    return {"cache": run_dir / "formal", "min_frames": manifest.get("min_frames"),
            "require_mechanism": bool(manifest.get("target_only"))}


def _flow(run_dir: Path, model, executor: Executor, context: str) -> dict:
    m = load(run_dir / "manifest.json")
    max_candidates, parallel = m["max_candidates"], m["parallel"]
    mode = {"target_only": m.get("target_only", False), "formal": formal_opts(run_dir, m)}
    seeds, skipped = seed_candidates(run_dir, m)
    cands, err = stage_a(run_dir, model, enumerate_prompt(context, mode["target_only"], max_candidates, seeds),
                         "stage_a", parse_target_candidates if mode["target_only"] else parse_candidates)
    cands = seeds + _number(first_candidates(cands or [], max_candidates, mode["target_only"]), len(seeds) + 1, 1)
    dump(run_dir / "candidates.json", {"passes": {"1": {"error": err}}, "candidates": cands, "unkillable": [],
                                       **({"seed_skipped": skipped} if m.get("seed") else {})})
    if (err and not seeds) or m["stage_a_only"]:
        return finish(run_dir, executor)
    for c in seeds:
        record_seed(run_dir, c, context, mode["target_only"])
    author_all(run_dir, model, executor, cands, context, parallel, **mode)
    set_stage(run_dir, executor, only={c["cid"] for c in cands}, formal=mode["formal"])
    if m["survivor_pass"]:
        prompt, remaining = survivor_prompt(run_dir, context)
        res, err2 = stage_a(run_dir, model, prompt, "stage_a2", lambda text: parse_survivor_answer(text, remaining))
        new, unk = res or ([], [])
        new = _number(new[:max_candidates], len(cands) + 1, 2)
        rec = load(run_dir / "candidates.json")
        rec["passes"]["2"] = {"error": err2, "remaining_survivors": remaining}
        rec["candidates"] += new
        rec["unkillable"] = unk
        dump(run_dir / "candidates.json", rec)
        author_all(run_dir, model, executor, new, context, parallel, **mode)
        set_stage(run_dir, executor, only={c["cid"] for c in new}, formal=mode["formal"])
    if m["write"]:
        write_accepted(run_dir, m["design"])
        dump(run_dir / "check.json", executor.check())
    return finish(run_dir, executor)


def _pid(cid: str) -> str:
    return "P" + str(int(cid[1:]))


def author_all(run_dir: Path, model, executor: Executor, cands: list[dict], context: str,
               parallel: int = 1, target_only: bool = False, formal: dict | None = None) -> None:
    """Stage B, `parallel` candidates at a time. Each conversation and its gate results are
    recorded under its own cid, and the set stage runs afterwards in cid order, so the
    decisions do not depend on the order the conversations finish in."""
    from concurrent.futures import ThreadPoolExecutor
    tasks = [c for c in cands if c.get("kind") == "task"]
    with ThreadPoolExecutor(max(1, parallel)) as pool:
        for f in [pool.submit(author, run_dir, model, executor, c, _pid(c["cid"]), context, target_only, formal)
                  for c in tasks]:
            f.result()


def author(run_dir: Path, model, executor: Executor, cand: dict, pid: str, context: str,
           target_only: bool = False, formal: dict | None = None) -> None:
    cid = cand["cid"]
    messages = author_messages(cand, context, target_only)
    for attempt in range(RETRIES + 1):
        text = _call(model, messages, run_dir / "responses" / cid / f"{attempt}.json")
        out = run_dir / "gates" / cid / f"{attempt}.json"
        fresh = not out.exists()
        try:
            res = gate_response(run_dir / "candidates" / cid / str(attempt), text, pid, executor,
                                out, run_dir / "base_pack", target_only, formal)
            if fresh:
                record_executor(run_dir, cid, str(attempt), executor)
        except InfraError as e:  # not a decision: stop this candidate, count nothing, resume retries it
            dump(run_dir / "infra" / f"{cid}.json", {"stage": "author", "attempt": attempt, "error": str(e)})
            return
        if res["accepted"] or attempt == RETRIES:
            return
        messages = [*messages, {"role": "assistant", "content": text},
                    {"role": "user", "content": repair_message(res)}]


def author_messages(cand: dict, context: str, target_only: bool) -> list[dict]:
    """The first Stage B message for a candidate (a seeded one too: its repair turns follow it)."""
    shown = {k: v for k, v in cand.items() if k not in ("cid", "pass", "seeded")}
    template = "author_target.md" if target_only else "author.md"
    return [{"role": "user", "content": fill((PROMPTS / template).read_text(), context=context,
                                             candidate=yaml.safe_dump(shown, sort_keys=False).strip())}]


# --- seeding --------------------------------------------------------------------------------

SEED_DIR = "seed"  # under the run: the copy of the run it was seeded from


def seed_candidates(run_dir: Path, manifest: dict) -> tuple[list[dict], list[str]]:
    """(seeded candidates, numbered from c01; source cids skipped for having no bundle).

    Every task candidate of the copied seed run with a bundle on disk, at its latest
    attempt (the last candidates/<cid>/<n>/ with an item.yaml, gated or not), with
    provenance seeded: {run, cid, attempt}. Read from the run's copy only, so the
    run, a resume and the replay all derive the same list."""
    if not manifest.get("seed"):
        return [], []
    src = run_dir / manifest["seed"]
    out, skipped = [], []
    for c in load(src / "candidates.json")["candidates"]:
        if c.get("kind") != "task":
            continue
        d = src / "candidates" / c["cid"]
        att = max((int(p.name) for p in d.glob("*") if (p / "item.yaml").is_file()), default=None)
        if att is None:
            skipped.append(c["cid"])
            continue
        shown = {k: v for k, v in c.items() if k not in ("cid", "pass", "seeded")}
        out.append({**shown, "seeded": {"run": src.name, "cid": c["cid"], "attempt": att}})
    return _number(out, 1, 1), skipped


def seed_bundle_text(run_dir: Path, manifest: dict, cand: dict) -> str:
    """A seeded candidate's bundle as a Stage B answer, with the ITEM token where the
    seed run's ID was: the text parse_bundle reads, and what repair turns follow."""
    s = cand["seeded"]
    src = run_dir / manifest["seed"] / "candidates" / s["cid"] / str(s["attempt"])
    item = yaml.safe_load((src / "item.yaml").read_text())
    pid = item["id"]
    plan = {k: v for k, v in item.items() if k not in ("id", "cover_module")}  # write_candidate adds them
    blocks = [("plan", yaml.safe_dump(plan, sort_keys=False)), ("cover", (src / "cover.sv").read_text())]
    if (src / "twin.sv").is_file():
        blocks.append(("twin", (src / "twin.sv").read_text()))
    out = ""
    for tag, body in blocks:
        out += f"<{tag}>\n" + substitute(body, pid, "ITEM").rstrip("\n") + f"\n</{tag}>\n"
    return out


def record_seed(run_dir: Path, cand: dict, context: str, target_only: bool) -> None:
    """Attempt 0 of a seeded candidate, recorded as a response with no model call; Stage B
    then gates it and continues with repair turns as for any candidate."""
    path = run_dir / "responses" / cand["cid"] / "0.json"
    rec = {"messages": author_messages(cand, context, target_only), "params": None, "seeded": cand["seeded"],
           "response": {"text": seed_bundle_text(run_dir, load(run_dir / "manifest.json"), cand)}}
    if path.exists():  # resume
        if load(path) != json.loads(json.dumps(rec)):
            raise RuntimeError(f"{path}: recorded seed differs from the one this code builds; cannot resume")
        return
    dump(path, rec)


_MANIFEST = threading.Lock()


def record_executor(run_dir: Path, cid: str, step: str, executor: Executor) -> None:
    """manifest.json executors: cid -> {attempt or "set": executor label}, for every gate
    this process ran (a resume or another executor may have decided the others).
    A replay's work directory has no manifest: replays are not recorded."""
    path = run_dir / "manifest.json"
    if not path.exists():
        return
    with _MANIFEST:
        m = load(path)
        m.setdefault("executors", {}).setdefault(cid, {})[step] = executor.label
        dump(path, m)


def gate_response(cand_dir: Path, text: str, pid: str, executor: Executor, out: Path,
                  base: Path, target_only: bool = False, formal: dict | None = None) -> dict:
    if out.exists():  # resume: gate results are a function of the response and the base pack
        return load(out)
    try:
        bundle = parse_bundle(text, target_only)
    except ParseError as e:
        res = format_failure(str(e))
        dump(out, res)
        return res
    if cand_dir.exists():
        shutil.rmtree(cand_dir)
    write_candidate(bundle, pid, cand_dir)
    res = executor.gate(cand_dir, out, base, formal)
    if bundle["yaml_fallback"]:  # the plan parsed only with its description quoted (parse_bundle)
        next(g for g in res["gates"] if g["gate"] == "format")["data"]["yaml_fallback"] = True
        dump(out, res)
    return res


def _final_attempt(run_dir: Path, cid: str) -> tuple[int, dict] | None:
    files = sorted((run_dir / "gates" / cid).glob("*.json"), key=lambda p: int(p.stem))
    return (int(files[-1].stem), load(files[-1])) if files else None


def witness_texts(run_dir: Path, res: dict) -> tuple[str | None, str | None]:
    """(reach gold, twin near-miss) of a gate result, rebuilt from the run's witness cache."""
    from closure_core import gates
    f = _gate_data(res, "formal")
    get = lambda key: {**load(run_dir / "formal" / f"{key}.json"), "key": key}
    gold = gates.reach_gold_text(get(f["key"]), f["bound"]) if f.get("gold_source") == "formal" else None
    twin = gates.twin_near_miss_text(get(f["twin"]["key"]), f["bound"]) if f.get("twin") else None
    return gold, twin


def set_stage(run_dir: Path, executor: Executor, base: Path | None = None,
              only: set[str] | None = None, formal: dict | None = None) -> None:
    """Gate accepted candidates in order against a cumulative pack (cross-candidate duplicates).

    only: gate just these; earlier candidates with a recorded set result are added
    to the pack as recorded (pass 2 builds on pass 1). The pack is the same as a
    single set stage over every candidate builds, which is what replay runs.
    """
    from closure_core import candidate
    from closure_core.gates import RESET_TIMING_CAP, declared_mechanisms
    setpack = run_dir / "setpack"
    if setpack.exists():
        shutil.rmtree(setpack)
    shutil.copytree(base or run_dir / "base_pack", setpack)
    reset_timing = 0  # accepted so far, in cid order
    for c in load(run_dir / "candidates.json")["candidates"]:
        fa = _final_attempt(run_dir, c["cid"])
        if not fa or not fa[1]["accepted"]:
            continue
        cand = run_dir / "candidates" / c["cid"] / str(fa[0])
        rec = run_dir / "set" / f"{c['cid']}.json"
        texts = witness_texts(run_dir, fa[1])
        rt = "reset_timing" in declared_mechanisms(yaml.safe_load((cand / "item.yaml").read_text()))
        if only is not None and c["cid"] not in only:
            if rec.exists() and load(rec)["accepted"]:
                candidate.add(setpack, cand, *texts)
                reset_timing += rt
            continue
        if not rec.exists() and rt and reset_timing >= RESET_TIMING_CAP:
            dump(rec, cap_rejection(fa[1]["item"]))
        try:
            if rec.exists():
                res = load(rec)
            else:
                res = executor.gate(cand, rec, base=setpack, formal=formal)
                record_executor(run_dir, c["cid"], "set", executor)
        except InfraError as e:
            # Later candidates are gated against this pack: skipping one would change their
            # duplicate decisions, so the run stops here and --resume continues in order.
            dump(run_dir / "infra" / f"{c['cid']}.json", {"stage": "set", "error": str(e)})
            raise
        if res["accepted"]:
            candidate.add(setpack, cand, *texts)
            reset_timing += rt
    shutil.rmtree(setpack)


def cap_rejection(item: str) -> dict:
    """Set-stage result for a reset_timing item over the per-run cap (not gated)."""
    from closure_core.gates import RESET_TIMING_CAP
    return {"item": item, "accepted": False, "failed_gate": "reset_timing_cap",
            "gates": [{"gate": "reset_timing_cap", "ok": False, "data": {},
                       "detail": f"at most {RESET_TIMING_CAP} items declaring reset_timing per run; "
                                 f"already accepted"}],
            "skipped": []}


def tree_sha(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(d)).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def write_from(run_dir: Path, executor: Executor) -> list[str]:
    """Write a finished run's accepted items into designs/ without new model calls.

    Refuses (returns the reasons) unless the run gated candidates and wrote
    nothing yet, designs/<d> is byte-identical to the run's base_pack (the pack
    every decision was made against), and a replay with the current code
    reproduces every decision. Then writes, runs tools/check, re-summarises.
    """
    manifest = load(run_dir / "manifest.json")
    design_name = manifest["design"]
    errs = []
    if manifest.get("stage_a_only") or not (run_dir / "set").is_dir():
        errs.append("the run has no set stage (stage-A-only or unfinished)")
    if (run_dir / "written.json").exists():
        errs.append("the run was already written (written.json exists)")
    if any((run_dir / "infra").glob("*.json")):
        errs.append("the run has infrastructure aborts (infra/); --resume it first")
    if not errs and tree_sha(ROOT / "designs" / design_name) != tree_sha(run_dir / "base_pack"):
        errs.append(f"designs/{design_name} differs from the run's base_pack; re-run the proposer")
    if not errs:
        errs += [f"replay: {d}" for d in replay(run_dir, executor)]
    if errs:
        return errs
    write_accepted(run_dir, design_name)
    dump(run_dir / "check.json", executor.check())
    finish(run_dir, executor)
    return []


def write_accepted(run_dir: Path, design_name: str) -> None:
    """Final IDs, provenance, and the files in the real pack (plan.yaml comments preserved)."""
    pack = ROOT / "designs" / design_name
    design = load_design(design_name)
    manifest = load(run_dir / "manifest.json")
    used = {it.id for it in design.plan}
    written = {}
    for c in load(run_dir / "candidates.json")["candidates"]:
        s = run_dir / "set" / f"{c['cid']}.json"
        if not s.exists() or not load(s)["accepted"]:
            continue
        att, res = _final_attempt(run_dir, c["cid"])
        src = run_dir / "candidates" / c["cid"] / str(att)
        pid = res["item"]
        m = re.search(r"\bbind\s+(\w+)\s+cov_", (src / "cover.sv").read_text())
        prefix = PREFIX.get(m.group(1) if m else "", "M")
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        final = f"{prefix}{n}"
        used.add(final)
        item = yaml.safe_load(substitute((src / "item.yaml").read_text(), pid, final))
        reach, twin = witness_texts(run_dir, res)
        if reach:
            item["gold_source"] = "formal"
        item["provenance"] = {"proposed_by": manifest["model"]["model"], "run_id": manifest["run_id"],
                              "candidate": c["cid"], "prompt_sha": manifest["prompt_sha"],
                              "status": "auto_accepted", "audited_by": None}
        entry = yaml.safe_dump([item], sort_keys=False, width=100)
        with (pack / "plan.yaml").open("a") as f:
            f.write("\n" + "\n".join("  " + line if line else line for line in entry.splitlines()) + "\n")
        (pack / "covers" / f"{final}.sv").write_text(substitute((src / "cover.sv").read_text(), pid, final))
        gold = reach if reach else (src / "gold.sv").read_text()  # a reach gold keeps its header first
        (pack / "gold" / f"{final}.sv").write_text(substitute(gold, pid, final))
        near = {p.name: p.read_text() for p in sorted((src / "near_miss").glob("*.sv"))}
        near |= {"twin.sv": twin} if twin else {}
        for name, text in near.items():
            (pack / "near_miss").mkdir(exist_ok=True)
            (pack / "near_miss" / f"{final}_{name}").write_text(substitute(text, pid, final))
        written[c["cid"]] = final
    dump(run_dir / "written.json", written)


# --- summary --------------------------------------------------------------------------------

def _passed(res: dict) -> list[str]:
    return [g["gate"] for g in res["gates"] if g["ok"] in (True, "n/a")]


def _gate_data(res: dict, gate: str) -> dict:
    return next((g["data"] for g in res["gates"] if g["gate"] == gate), {}) or {}


def _funnel(results: list[dict]) -> list[dict]:
    out = [{"gate": g, "passed": sum(g in _passed(r) for r in results)} for g in GATES]
    nm = next(f for f in out if f["gate"] == "near_miss")
    # Opt-outs pass the gate without a near-miss; counted so they cannot hide in "passed".
    nm["opted_out"] = sum(bool(_gate_data(r, "near_miss").get("opted_out")) for r in results)
    return out


def remaining_survivors(before: dict, accepted: dict[str, dict]) -> list[str]:
    killed = set(before["killed_by_plan"]) | {m for r in accepted.values() for m in _gate_data(r, "value").get("kills", [])}
    return sorted(set(before["survivors"]) - killed)


def advance(before: dict, accepted: dict[str, dict]) -> dict:
    """progress_before as it stands after these candidates are added (for pass 2)."""
    rs = list(accepted.values())
    return {**before,
            "killed_by_plan": sorted((set(before["killed_by_plan"]) | {m for r in rs for m in _gate_data(r, "value")
                                      .get("kills", [])}) & set(before["survivors"])),
            "closed_by_plan": sorted(set(before["closed_by_plan"]) | {h for r in rs for h in _gate_data(r, "gold")
                                                                      .get("holes_hit", [])}),
            "requirements_by_plan": sorted(set(before["requirements_by_plan"]) | {q for r in rs for q in _gate_data(
                r, "value").get("requirement_keys", [])})}


def progress(before: dict, accepted: dict[str, dict]) -> dict:
    """What the accepted candidates (cid -> final gate result) add to the existing plan,
    on three mechanical proxies.

    No hand-written reference list: survivors and holes are computed from the
    baseline, requirement sentences from the verified citations. Each candidate
    is gated against the plan, not against the other candidates, so its value
    detail ("only by this gold") ignores them; `per_candidate` and `shared`
    give the kills within the run.
    """
    surv, k0 = set(before["survivors"]), set(before["killed_by_plan"])
    kills = {cid: set(_gate_data(r, "value").get("kills", [])) & surv - k0 for cid, r in accepted.items()}
    k1 = set().union(*kills.values()) if kills else set()
    killers = {m: sorted(c for c, ks in kills.items() if m in ks) for m in k1}
    accepted = list(accepted.values())
    holes = set(before["holes"]) - set(before["waived_holes"])
    c0 = set(before["closed_by_plan"]) & holes
    c1 = {h for r in accepted for h in _gate_data(r, "gold").get("holes_hit", [])} & holes
    r0 = set(before["requirements_by_plan"])
    r1 = {q for r in accepted for q in _gate_data(r, "value").get("requirement_keys", [])}
    return {
        "mutants": {"baseline_survivors": len(surv), "killed_by_plan": len(k0),
                    "killed_by_run": sorted(k1), "remaining": len(surv - k0 - k1),
                    # Sum of per-candidate kills >= killed_by_run; the difference is overlap.
                    "per_candidate": {c: {"kills": len(ks), "only_this_candidate":
                                          sum(killers[m] == [c] for m in ks)} for c, ks in sorted(kills.items())},
                    "shared": {m: cs for m, cs in sorted(killers.items()) if len(cs) > 1}},
        "holes": {"baseline": len(before["holes"]), "waived": len(before["waived_holes"]),
                  "closed_by_plan": len(c0), "closed_by_run": sorted(c1 - c0),
                  "remaining": sorted(holes - c0 - c1)},
        # No "remaining": the documents' requirement sentences are not enumerated.
        "requirements": {"cited_by_plan": len(r0), "new_in_run": sorted(r1 - r0)},
    }


def _pass_summary(run_dir: Path, tasks: list[dict], set_res: dict, before: dict) -> dict:
    first, final = {}, {}
    for c in tasks:
        p = run_dir / "gates" / c["cid"] / "0.json"
        if p.exists():
            first[c["cid"]] = load(p)
            final[c["cid"]] = _final_attempt(run_dir, c["cid"])[1]
    sets = {cid: set_res[cid] for cid in final if cid in set_res}
    failed_first = [cid for cid, r in first.items() if not r["accepted"]]
    repaired = sum(final[cid]["accepted"] for cid in failed_first)
    accepted = {cid: final[cid] for cid, r in sets.items() if r["accepted"]}
    return {
        # Gates stop at the first failure, so each gate only sees candidates that passed
        # the ones before it: read these as a funnel, not as independent rates.
        "funnel_first_attempt": [{"gate": "proposed", "passed": len(first)}, *_funnel(list(first.values()))],
        "funnel_final": [{"gate": "proposed", "passed": len(final)}, *_funnel(list(final.values())),
                         {"gate": "set_duplicate", "passed": sum(r["accepted"] for r in sets.values())}],
        "rejected_at": {cid: r["failed_gate"] for cid, r in final.items() if not r["accepted"]},
        "rejected_at_set": {cid: r["failed_gate"] for cid, r in sets.items() if not r["accepted"]},
        # Measured false-rejection risk of the value gate: everything else passed.
        "rejected_solely_for_value": sorted(cid for cid, r in final.items() if r["failed_gate"] == "value"),
        "repair": {"failed_first_attempt": len(failed_first), "repaired": repaired,
                   "rate": round(repaired / len(failed_first), 3) if failed_first else None},
        "accepted": sorted(accepted),
        "progress": progress(before, accepted),
    }, accepted


def summarize(run_dir: Path) -> dict:
    rec = load(run_dir / "candidates.json")
    infra = {p.stem: load(p) for p in sorted((run_dir / "infra").glob("*.json"))}
    # Infrastructure aborts are not decisions: those candidates are left out of every count.
    cands = [c for c in rec["candidates"] if c["cid"] not in infra]
    pack = load(run_dir / "context_pack.json")
    before = _before(run_dir)
    tasks = [c for c in cands if c.get("kind") == "task"]
    set_res = {p.stem: load(p) for p in sorted((run_dir / "set").glob("*.json"))}
    context_pages = {(d, p["page"]) for d, doc in pack["docs"].items() for p in doc["pages"]}
    registry = yaml.safe_load((ROOT / "designs" / pack["design"] / "sources.yaml").read_text())["documents"]
    pages = {(d, p["page"]) for d, m in registry.items() for p in m.get("context_pages", [])}
    cited = {c["cid"]: sorted({(s.get("doc"), s.get("page")) for s in c.get("sources") or []
                               if isinstance(s, dict) and s.get("type") == "DOC"}) for c in cands}
    passes, acc_all, pass_before = {}, {}, before
    for n in sorted(rec["passes"], key=int):
        ps, acc = _pass_summary(run_dir, [c for c in tasks if c["pass"] == int(n)], set_res, pass_before)
        attempts = len(list((run_dir / "responses" / ("stage_a" if n == "1" else "stage_a2")).glob("*.json")))
        passes[n] = {"stage_a": {"attempts": attempts, "error": rec["passes"][n]["error"]}, **ps}
        acc_all.update(acc)
        pass_before = advance(pass_before, acc)
    final = {c["cid"]: _final_attempt(run_dir, c["cid"])[1] for c in tasks if _final_attempt(run_dir, c["cid"])}
    s = {
        "run_id": run_dir.name,
        "infra_aborted": {cid: r["error"] for cid, r in infra.items()},
        "proposed": {"tasks": len(tasks), "waivers": len(cands) - len(tasks),
                     "by_pass": {n: sum(c["pass"] == int(n) for c in tasks) for n in passes}},
        "waiver_proposals": [{k: c.get(k) for k in ("cid", "title", "behaviour", "why_baseline_misses")}
                             for c in cands if c.get("kind") != "task"],
        "passes": passes,
        "accepted": sorted(acc_all),
        "progress_total": progress(before, acc_all),
        # Always in the audit sample: no near-miss, only a written reason.
        "near_miss_opt_outs": {cid: _gate_data(r, "near_miss")["opted_out"] for cid, r in acc_all.items()
                               if _gate_data(r, "near_miss").get("opted_out")},
        "hit_by_random": {cid: _gate_data(r, "baseline")["hit_by_random"] for cid, r in acc_all.items()
                          if _gate_data(r, "baseline").get("hit_by_random")},
        "mechanisms": {m: sorted(cid for cid, r in acc_all.items() if m in _gate_data(r, "mechanism").get("mechanisms", []))
                       for m in sorted({m for r in acc_all.values() for m in _gate_data(r, "mechanism").get("mechanisms", [])})},
        # Formal witnesses of accepted candidates: reach golds (the length in frames is the
        # hardening signal, the depth in cycles a recorded measure) and twin near-misses.
        "witnesses": {cid: {"gold_source": f["gold_source"], "witness_depth": f.get("witness_depth"),
                            "witness_frames": f.get("witness_frames"), "active_frames": f.get("active_frames"),
                            "input_changes": f.get("input_changes"),
                            "twin_depth": (f.get("twin") or {}).get("witness_depth")}
                      for cid, r in acc_all.items()
                      if (f := _gate_data(r, "formal")).get("gold_source") == "formal" or f.get("twin")},
        "cited_doc_pages": {cid: [f"{d} p{p}" for d, p in v] for cid, v in cited.items() if v},
        "cites_outside_context_pages": sorted(cid for cid, v in cited.items() if set(v) - pages),
        "context_pages": sorted(f"{d} p{p}" for d, p in context_pages) if not pack["full_docs"] else "full documents",
    }
    if rec.get("seed_skipped") is not None:
        s["seeded"] = {c["cid"]: c["seeded"] for c in cands if c.get("seeded")}
        s["seed_skipped"] = rec["seed_skipped"]
    if "2" in rec["passes"]:
        targets = {c["cid"]: sorted(map(str, c.get("targets") or [])) for c in tasks if c["pass"] == 2}
        s["survivor_pass"] = {
            "remaining_before": len(rec["passes"]["2"].get("remaining_survivors") or []),
            # Did each gold kill what its candidate said it targets? (any final attempt, accepted or not)
            "targets_killed": {cid: sorted(set(ts) & set(_gate_data(final[cid], "value").get("kills", [])))
                               for cid, ts in targets.items() if cid in final},
            "targets": targets,
            # Recorded for review only; never turned into waivers.
            "unkillable": {str(u["mutant"]): u["reason"] for u in rec.get("unkillable") or []},
        }
    if (run_dir / "written.json").exists():
        s["written"] = load(run_dir / "written.json")
    if (run_dir / "check.json").exists():
        s["check_exit"] = load(run_dir / "check.json")["exit"]
    return s


def finish(run_dir: Path, executor: Executor) -> dict:
    """Summarise; first measure the existing plan's progress if the context pack left it out
    (on the run's base_pack, so the numbers match a run that measured it at startup)."""
    if "progress_before" not in load(run_dir / "context_pack.json") and not (run_dir / "progress_before.json").exists():
        executor.progress_before(run_dir / "progress_before.json", run_dir / "base_pack")
    s = summarize(run_dir)
    dump(run_dir / "summary.json", s)
    return s


# --- replay ---------------------------------------------------------------------------------

def _replay_stage_a(run_dir: Path, tag: str, parse, diffs: list[str]) -> tuple[object | None, str | None]:
    """Re-parse every recorded Stage A attempt; checks the repair messages it re-derives."""
    att, out = 0, (None, None)
    while (f := run_dir / "responses" / tag / f"{att}.json").exists():
        try:
            out = (parse(load(f)["response"]["text"]), None)
        except ParseError as e:
            out = (None, str(e))
        nxt = run_dir / "responses" / tag / f"{att + 1}.json"
        if nxt.exists() and (out[1] is None or load(nxt)["messages"][-1]["content"] != stage_a_repair(out[1])):
            diffs.append(f"{tag} attempt {att + 1}: repair message differs")
        att += 1
    return out


def _replay_stage_b(run_dir: Path, work: Path, cands: list[dict], executor: Executor, diffs: list[str],
                    target_only: bool = False, formal: dict | None = None) -> None:
    for c in cands:
        if c.get("kind") != "task":
            continue
        cid, att = c["cid"], 0
        while (resp := run_dir / "responses" / cid / f"{att}.json").exists():
            if not (run_dir / "gates" / cid / f"{att}.json").exists():
                break  # aborted as infrastructure in the run: nothing was decided
            try:
                res = gate_response(work / "candidates" / cid / str(att), load(resp)["response"]["text"],
                                    _pid(cid), executor, work / "gates" / cid / f"{att}.json",
                                    run_dir / "base_pack", target_only, formal)
            except InfraError as e:
                diffs.append(f"{cid} attempt {att}: infrastructure abort in replay (not a decision): {e}")
                break
            if res != load(run_dir / "gates" / cid / f"{att}.json"):
                diffs.append(f"{cid} attempt {att}: gate result differs")
            nxt = run_dir / "responses" / cid / f"{att + 1}.json"
            if nxt.exists() and load(nxt)["messages"][-1]["content"] != repair_message(res):
                diffs.append(f"{cid} attempt {att + 1}: repair message differs")
            att += 1


def replay(run_dir: Path, executor: Executor) -> list[str]:
    """Re-gate every recorded response; returns mismatches (empty = reproduced).

    Follows the run: pass 1 Stage A, Stage B and set stage; then (if recorded)
    the pass 2 prompt is rebuilt from the replayed pass 1 results and must equal
    the recorded one, then pass 2 Stage A, Stage B and set stage.
    """
    work = run_dir / "replay"
    if work.exists():
        shutil.rmtree(work)
    again = work / "run"
    again.mkdir(parents=True)
    diffs: list[str] = []
    manifest, rec = load(run_dir / "manifest.json"), load(run_dir / "candidates.json")
    for f in ("candidates.json", "context_pack.json", "progress_before.json"):
        if (run_dir / f).exists():
            shutil.copy(run_dir / f, again / f)
    shutil.copytree(run_dir / "responses", again / "responses")  # inputs: the summary counts attempts
    if (run_dir / "formal").exists():  # recorded witnesses: replay does not re-solve
        shutil.copytree(run_dir / "formal", again / "formal")
    if (run_dir / "infra").exists():  # the run's aborts: those candidates are not counted in either
        shutil.copytree(run_dir / "infra", again / "infra")
    target_only, formal = manifest.get("target_only", False), formal_opts(again, manifest)
    recorded = {n: [c for c in rec["candidates"] if c["pass"] == int(n)] for n in rec["passes"]}

    def sync() -> None:
        for d in ("candidates", "gates"):
            if (work / d).exists():
                shutil.copytree(work / d, again / d, dirs_exist_ok=True)

    seeds, skipped = seed_candidates(run_dir, manifest)
    if manifest.get("seed"):  # the seeded list shown at Stage A, and each seeded attempt 0
        context = render_context(load(run_dir / "context_pack.json"), (PROMPTS / "rules.md").read_text(),
                                 target_only)
        a = load(run_dir / "responses" / "stage_a" / "0.json")["messages"][0]["content"]
        if a != enumerate_prompt(context, target_only, manifest["max_candidates"], seeds):
            diffs.append("stage A (pass 1): prompt differs (seeded candidates changed)")
        for c in seeds:
            if load(run_dir / "responses" / c["cid"] / "0.json")["response"]["text"] != \
                    seed_bundle_text(run_dir, manifest, c):
                diffs.append(f"{c['cid']} attempt 0: seeded bundle differs")
    cands, err = _replay_stage_a(run_dir, "stage_a", parse_target_candidates if target_only else parse_candidates,
                                 diffs)
    cands = seeds + _number(first_candidates(cands or [], manifest["max_candidates"], target_only),
                            len(seeds) + 1, 1)
    if cands != recorded["1"] or err != rec["passes"]["1"]["error"] or skipped != rec.get("seed_skipped", []):
        return diffs + ["stage A (pass 1): parsed candidates differ from candidates.json"]
    _replay_stage_b(run_dir, work, cands, executor, diffs, target_only, formal)
    sync()
    if (run_dir / "set").exists():
        set_stage(again, executor, run_dir / "base_pack", only={c["cid"] for c in cands}, formal=formal)
    if "2" in rec["passes"]:
        context = render_context(load(run_dir / "context_pack.json"), (PROMPTS / "rules.md").read_text(),
                                 target_only)
        prompt, remaining = survivor_prompt(again, context)
        if load(run_dir / "responses" / "stage_a2" / "0.json")["messages"][0]["content"] != prompt:
            diffs.append("stage A (pass 2): prompt differs (pass 1 results or survivors changed)")
        res, err2 = _replay_stage_a(run_dir, "stage_a2", lambda x: parse_survivor_answer(x, remaining), diffs)
        new, unk = res or ([], [])
        new = _number(new[:manifest["max_candidates"]], len(cands) + 1, 2)
        if (new != recorded["2"] or unk != rec["unkillable"] or err2 != rec["passes"]["2"]["error"]
                or remaining != rec["passes"]["2"]["remaining_survivors"]):
            return diffs + ["stage A (pass 2): parsed answer differs from candidates.json"]
        _replay_stage_b(run_dir, work, new, executor, diffs, target_only, formal)
        sync()
        set_stage(again, executor, run_dir / "base_pack", only={c["cid"] for c in new}, formal=formal)
    for p in sorted((run_dir / "set").glob("*.json")):
        q = again / "set" / p.name
        if (again / "infra" / p.name).exists() and not (run_dir / "infra" / p.name).exists():
            diffs.append(f"set {p.stem}: infrastructure abort in replay (not a decision)")
        elif not q.exists() or load(q) != load(p):
            diffs.append(f"set {p.stem}: result differs")
    run_only = ("run_id", "written", "check_exit")  # not decisions the gates make
    strip = lambda s: {k: v for k, v in s.items() if k not in run_only}
    if strip(summarize(again)) != strip(load(run_dir / "summary.json")):
        diffs.append("summary of the replayed results differs from summary.json")
    if not diffs:
        shutil.rmtree(work)
    return diffs
