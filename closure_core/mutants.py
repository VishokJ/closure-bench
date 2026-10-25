"""Fixed-operator RTL mutants for the mutation gate.

Each mutant changes exactly one line inside a design's always blocks (the line
ranges come from design.yaml `mutate:`). No randomness: the list depends only
on the RTL text, and IDs are stable: <file>:<line>:<op>:<occurrence>.

Operators:
  relational swap   == != > >= < <=, only inside if (...) conditions, because
                    `<=` outside a condition is a non-blocking assignment
  inv               if (c) -> if (!(c))
  inc / dec         decimal literal +1 / -1 (not sized literals, not bit selects)
  stuck0 / stuck1   right-hand side of a non-blocking assignment -> 0 / 1
  drop              non-blocking assignment -> empty statement
"""

from __future__ import annotations

import functools
import hashlib
import platform
import re
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from closure_core import grader, sim
from closure_core.design import Design

REL_SWAP = {"==": "!=", "!=": "==", ">": ">=", ">=": ">", "<": "<=", "<=": "<"}
REL_NAME = {"==": "eq_ne", "!=": "ne_eq", ">": "gt_ge", ">=": "ge_gt", "<": "lt_le", "<=": "le_lt"}
REL_OPS = set(REL_NAME.values())

IF_RE = re.compile(r"\bif\s*\(")
# Longest first, so shifts are recognised (and skipped) before < and >.
OP_RE = re.compile(r"<<|>>|==|!=|>=|<=|<|>")
LHS = r"(?:\{[^}]*\}|[A-Za-z_]\w*(?:\[[^\]]*\])?)"
ASSIGN_RE = re.compile(rf"^(\s*)({LHS})(\s*<=\s*)(.+?);\s*$")
DEC_RE = re.compile(r"(?<![\w'.])\d+(?![\w'.])")
MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.M)
ZERO = {"0", "1'b0", "'0", "1'd0"}
ONE = {"1", "1'b1", "1'd1"}


@dataclass(frozen=True)
class Mutant:
    id: str
    file: str       # RTL file name, e.g. uart_rx.v
    module: str     # module defined in that file
    line: int       # 1-based
    op: str
    original: str   # the original line
    mutated: str    # its replacement


def _code(line: str) -> tuple[str, str]:
    """Split a line into code and trailing // comment."""
    i = line.find("//")
    return (line, "") if i < 0 else (line[:i], line[i:])


def _condition(code: str) -> tuple[int, int] | None:
    """Span (start, end) of the text inside the first if (...), or None."""
    m = IF_RE.search(code)
    if not m:
        return None
    depth = 1
    for i in range(m.end(), len(code)):
        depth += {"(": 1, ")": -1}.get(code[i], 0)
        if depth == 0:
            return m.end(), i
    return None  # condition continues on the next line: not mutated


def _bracket_spans(code: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\[[^\]]*\]", code)]


def _line_mutants(code: str) -> list[tuple[str, str]]:
    """(op, mutated code) pairs for one line of code, in a fixed order."""
    out = []
    cond = _condition(code)
    if cond:
        lo, hi = cond
        for m in OP_RE.finditer(code, lo, hi):
            if m.group() in REL_SWAP:
                out.append((REL_NAME[m.group()],
                            code[:m.start()] + REL_SWAP[m.group()] + code[m.end():]))
        out.append(("inv", f"{code[:lo]}!({code[lo:hi]}){code[hi:]}"))

    a = ASSIGN_RE.match(code)
    const_rhs = a and not cond and DEC_RE.fullmatch(a.group(4).strip())
    brackets = _bracket_spans(code)
    for m in DEC_RE.finditer(code):
        # A constant right-hand side is covered by stuck0/stuck1 below.
        if const_rhs or any(s <= m.start() < e for s, e in brackets):
            continue
        n = int(m.group())
        out.append(("inc", code[:m.start()] + str(n + 1) + code[m.end():]))
        if n > 0:
            out.append(("dec", code[:m.start()] + str(n - 1) + code[m.end():]))

    if a and not cond:
        indent, lhs, arrow, rhs = a.groups()
        rhs = rhs.strip()
        if rhs not in ZERO:
            out.append(("stuck0", f"{indent}{lhs}{arrow}0;"))
        if rhs not in ONE:
            out.append(("stuck1", f"{indent}{lhs}{arrow}1;"))
        out.append(("drop", f"{indent};"))
    return out


def generate(path: Path, lo: int, hi: int) -> list[Mutant]:
    """All mutants of lines lo..hi (1-based, inclusive) of one RTL file."""
    text = path.read_text()
    module = MODULE_RE.search(text).group(1)
    lines = text.splitlines()
    out = []
    for n in range(lo, min(hi, len(lines)) + 1):
        line = lines[n - 1]
        code, comment = _code(line)
        seen: dict[str, int] = {}
        texts = {code}
        for op, mutated in _line_mutants(code):
            if mutated in texts:
                continue  # same line text as the original or an earlier mutant
            texts.add(mutated)
            k = seen.get(op, 0)
            seen[op] = k + 1
            out.append(Mutant(f"{path.name}:{n}:{op}:{k}", path.name, module, n, op,
                              line, mutated + comment))
    return out


def apply(text: str, m: Mutant) -> str:
    lines = text.splitlines(keepends=True)
    old = lines[m.line - 1]
    if old.rstrip("\r\n") != m.original:
        raise ValueError(f"{m.id}: line {m.line} does not match the mutant's original")
    lines[m.line - 1] = m.mutated + old[len(old.rstrip("\r\n")):]
    return "".join(lines)


def sha256(*parts: str | bytes) -> str:
    """Hash of every input that determines a simulation result."""
    h = hashlib.sha256()
    for p in parts:
        b = p.encode() if isinstance(p, str) else p
        h.update(len(b).to_bytes(8, "big") + b)
    return h.hexdigest()


@functools.cache
def _toolchain() -> str:
    return sim.verilator_version()


def cache_key(rtl: dict[Path, str], tb_text: str, top: str, run_timeout: float) -> str:
    """Hash of every compiled input: (mutated) RTL, testbench, driver, flags,
    toolchain, platform and run timeout. Covers are not compiled, so not hashed."""
    return sha256(*(f"{p.name}\0{t}" for p, t in rtl.items()),
                  top, tb_text, sim.SIM_MAIN.read_bytes(), " ".join(sim.VERILATOR_FLAGS),
                  _toolchain(), platform.machine(), str(run_timeout))


def simulate(design: Design, tb_text: str, top: str, mutant: Mutant | None = None, *,
             run_timeout: float = 20.0, cache: dict | None = None) -> dict:
    """Run one testbench against the RTL, optionally with one mutant applied.

    Compiled without covers: a mutant's status depends only on the RTL and the
    testbench, so cached results stay valid when covers are added or changed.

    Returns {"status": sim status, "modules": design modules the testbench
    instantiates (from line coverage)}. Cached under cache_key().
    """
    rtl = {p: p.read_text() for p in design.rtl}
    if mutant:
        target = next(p for p in rtl if p.name == mutant.file)
        rtl[target] = apply(rtl[target], mutant)
    key = cache_key(rtl, tb_text, top, run_timeout)
    if cache is not None and key in cache:
        return cache[key]
    with tempfile.TemporaryDirectory(prefix="cb-mut-") as d:
        paths = []
        for p, t in rtl.items():
            (Path(d) / p.name).write_text(t)
            paths.append(Path(d) / p.name)
        s = grader.simulate(replace(design, rtl=tuple(paths), covers=(), plan=()), tb_text,
                            top=top, run_timeout=run_timeout)
    res = {"status": s.sim.status,
           "modules": sorted({p.module for p in s.points if p.kind == "v_line"})}
    if cache is not None:
        cache[key] = res
    return res
