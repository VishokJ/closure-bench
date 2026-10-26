"""Formal measurement of cover points with Yosys + SymbiYosys.

Formal suggests, Verilator decides. This module finds the shortest legal input
trace (a witness) that reaches a cover, or reports that none exists within the
bound, and converts the witness into a testbench. It never decides a reward or
a gate: a witness counts only after the existing grader confirms, under
Verilator, that its testbench hits the cover.

The legal stimulus is the design pack's hand-reviewed formal environment,
designs/<name>/formal/ (formal.yaml plus one env file per bound module).

Open-source Yosys supports neither `cover property (@(posedge clk) ...)` nor
`bind`, so the cover file is translated into a formal-only copy:
  LABEL: cover property (@(posedge clk) disable iff (c) e);
    -> always @(posedge clk) if (!(c)) LABEL: cover (e);
  bind T C I (...);
    -> the instance C I (...) inserted at the end of a temporary copy of module T
Tracking logic is copied unchanged. covers/*.sv and the RTL are never edited.

Runs where the formal tools are (the toolchain image: /opt/oss-cad-suite, not
on PATH; CLOSURE_BENCH_FORMAL overrides).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

from closure_core.design import load_design

FORMAL_HOME = Path(os.environ.get("CLOSURE_BENCH_FORMAL", "/opt/oss-cad-suite"))
ENGINE = "smtbmc yices"


class UnsupportedCover(ValueError):
    """The cover uses a construct this translation does not handle."""


# --- cover translation ------------------------------------------------------------------------

_COVER = re.compile(r"(\w+)\s*:\s*cover\s+property\s*\(")
_BIND = re.compile(r"^\s*bind\s+(\w+)\s+(\w+)\s+(\w+)\s*(\((?:[^;])*\))\s*;", re.M)


def _balanced(text: str, i: int) -> int:
    """Index just past the parenthesis that closes the one at text[i]."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
    raise UnsupportedCover("unbalanced parentheses")


def translate_cover(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(formal-only cover text, binds as [(target module, instance text)]).

    Raises UnsupportedCover for any concurrent construct other than a labelled
    `cover property (@(posedge clk) [disable iff (c)] e);`.
    """
    binds = [(m.group(1), f"{m.group(2)} {m.group(3)} {m.group(4)};") for m in _BIND.finditer(text)]
    text = _BIND.sub("", text)
    out, pos = [], 0
    for m in _COVER.finditer(text):
        if m.start() < pos:
            continue
        open_i = m.end() - 1
        close_i = _balanced(text, open_i)
        if not re.match(r"\s*;", text[close_i:]):
            raise UnsupportedCover(f"{m.group(1)}: expected ';' after the cover")
        body = text[open_i + 1:close_i - 1].strip()
        clk = re.match(r"@\s*\(\s*posedge\s+(\w+)\s*\)\s*", body)
        if not clk:
            raise UnsupportedCover(f"{m.group(1)}: only @(posedge <clk>) clocking is supported")
        rest = body[clk.end():]
        cond = None
        dis = re.match(r"disable\s+iff\s*\(", rest)
        if dis:
            end = _balanced(rest, dis.end() - 1)
            cond, rest = rest[dis.end():end - 1].strip(), rest[end:].strip()
        guard = f"if (!({cond})) " if cond else ""
        out.append(text[pos:m.start()])
        out.append(f"always @(posedge {clk.group(1)}) {guard}{m.group(1)}: cover ({rest});")
        pos = close_i + len(re.match(r"\s*;", text[close_i:]).group(0))
    out.append(text[pos:])
    formal = "".join(out)
    left = re.search(r"\b(property|sequence|assert|assume|expect|restrict)\b|##|\|->|\|=>",
                     _strip_comments(formal))
    if left:
        raise UnsupportedCover(f"unsupported construct {left.group(0)!r}")
    return formal, binds


def _strip_comments(text: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)


def _insert_instance(rtl: str, module: str, instance: str) -> str:
    m = re.search(rf"^\s*module\s+{module}\b", rtl, re.M)
    if not m:
        raise ValueError(f"module {module} not found")
    end = re.search(r"^\s*endmodule\b", rtl[m.end():], re.M)
    i = m.end() + end.start()
    return rtl[:i] + f"\n// formal-only: emulates `bind {module}`\n{instance}\n" + rtl[i:]


# --- formal run -------------------------------------------------------------------------------

def _measure_wrapper(top: dict) -> str:
    """Formal top around the env: counts input changes (a bus counts once; step 0 excluded)
    and bounds them by MAX_CHANGES, for the minimisation."""
    ins = top["inputs"]
    decl = ",\n".join(f"  input wire {f'[{w - 1}:0] ' if w > 1 else ''}{n}" for n, w in ins.items())
    conn = ", ".join(f".{n}({n})" for n in ["clk", *ins])
    prev = "\n".join(f"  reg {f'[{w - 1}:0] ' if w > 1 else ''}prev_{n};\n"
                     f"  always @(posedge clk) prev_{n} <= {n};" for n, w in ins.items())
    delta = " + ".join(f"{{15'd0, {n} != prev_{n}}}" for n in ins)
    return f"""// Generated by closure_core/formal.py: measurement only, no stimulus rules here.
module formal_measure #(parameter [15:0] MAX_CHANGES = 16'hFFFF) (
  input wire clk,
{decl}
);
  {top['module']} env ({conn});
  reg first = 1'b1;
  always @(posedge clk) first <= 1'b0;
{prev}
  wire [15:0] delta = first ? 16'd0 : ({delta});
  reg [15:0] changes = 16'd0;
  always @(posedge clk) changes <= changes + delta;
  always @(*) assume(changes + delta <= MAX_CHANGES);
endmodule
"""


def _sby(work: Path, files: list[str], depth: int, timeout: float, max_changes: int | None,
         *, mode: str = "cover", top: str = "formal_measure") -> tuple[str, Path]:
    """Run one SymbiYosys job; (status, job dir).
    status: PASS | FAIL | UNKNOWN (prove: induction inconclusive) | TIMEOUT | ERROR."""
    name = f"job_{mode}_d{depth}_k{'inf' if max_changes is None else max_changes}"
    reads = "\n".join(f"read_verilog -formal -sv {f}" for f in files)
    chparam = f"chparam -set MAX_CHANGES {max_changes} formal_measure\n" if max_changes is not None else ""
    (work / f"{name}.sby").write_text(f"""[options]
mode {mode}
depth {depth}
timeout {max(1, int(timeout))}

[engines]
{ENGINE}

[script]
{reads}
{chparam}prep -top {top}
setundef -zero -init

[files]
{chr(10).join(files)}
""")
    try:
        subprocess.run([str(FORMAL_HOME / "bin" / "sby"), "-f", f"{name}.sby"], cwd=work,
                       capture_output=True, text=True, timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", work / name
    status = (work / name / "status").read_text().split()[0] if (work / name / "status").exists() else "ERROR"
    return status, work / name


def _read_witness(job: Path, top: dict) -> list[dict[str, int]]:
    """Per-step input values from the job's Yosys witness (trace0.yw)."""
    w = json.loads((job / "engine_0" / "trace0.yw").read_text())
    layout, off = [], 0
    for s in w["signals"]:
        name = s["path"][-1].lstrip("\\")
        if s.get("init_only"):
            raise RuntimeError(f"witness depends on the free initial value of {name}; "
                               "setundef -zero -init should have removed it")
        layout.append((name, off, s["width"]))
        off += s["width"]
    steps = []
    for st in w["steps"]:
        # The bit string is one vector, most significant bit first; signal 0 is at the
        # least significant end. Don't-care bits ('x', '?') are driven 0.
        v = int(re.sub(r"[^01]", "0", st["bits"]) or "0", 2)
        vals = {n: (v >> o) & ((1 << wd) - 1) for n, o, wd in layout}
        steps.append({n: vals[n] for n in top["inputs"]})
    return steps


def _changes(steps: list[dict[str, int]]) -> int:
    return sum(a[n] != b[n] for a, b in zip(steps, steps[1:]) for n in a)


def witness_testbench(steps: list[dict[str, int]], top: dict, dut: str, label: str) -> str:
    """A testbench in our conventions replaying the witness on the DUT's ports.

    Step k's inputs are sampled at the k-th rising edge: step 0 holds from time
    0, step k >= 1 is driven on the falling edge after rising edge k-1.
    """
    ins, outs = top["inputs"], top["outputs"]

    def lit(n: str, v: int) -> str:
        return f"{ins[n]}'d{v}"

    def vec(w: int) -> str:
        return f"[{w - 1}:0] " if w > 1 else ""

    lines = [f"// Formal witness for {label} (closure_core/formal.py): the shortest legal input",
             f"// trace Yosys/SymbiYosys found ({len(steps)} cycles), replayed on the {dut} ports.",
             "// A gold candidate, never shown to an agent; Verilator decides whether it hits.",
             "`timescale 1ns / 1ps", "", "module tb;", "  logic clk = 1'b0;", "  always #5 clk = ~clk;"]
    lines += [f"  logic {vec(w)}{n} = {lit(n, steps[0][n])};" for n, w in ins.items()]
    lines += [f"  wire  {vec(w)}{n};" for n, w in outs.items()]
    ports = ", ".join(f".{n}({n})" for n in ["clk", *ins, *outs])
    lines += ["", f"  {dut} dut ({ports});", "", "  initial begin"]
    wait = 0
    for prev, cur in zip(steps, steps[1:]):
        wait += 1
        diff = [n for n in ins if cur[n] != prev[n]]
        if diff:
            lines.append(f"    repeat ({wait}) @(negedge clk);" if wait > 1 else "    @(negedge clk);")
            lines.append("    " + " ".join(f"{n} = {lit(n, cur[n])};" for n in diff))
            wait = 0
    lines += [f"    repeat ({wait + 2}) @(negedge clk);", "    $finish;", "  end", "endmodule", ""]
    return "\n".join(lines)


def cover_witness(pack_dir: Path | str, cover_file: Path | str, *, bound: int = 300,
                  timeout: float = 600.0) -> dict:
    """Shortest legal witness for the single cover in cover_file, within `bound` cycles.

    Returns {status: reachable | unreachable | timeout, depth, input_changes, tb_text}
    plus: label, bound_module, solve_s (first solve), input_changes_exact, total_s.
    depth: witness length in clock cycles, from the reset cycle through the edge at
    which Yosys samples the cover true (one step after the cycle its condition holds:
    a constant offset, the same for every item); minimal, since the search goes step
    by step. input_changes: the fewest
    input changes (a bus counts once, rst included) among witnesses of that
    depth; exact unless the time budget ran out during the minimisation.
    `unreachable` means not reachable within `bound` cycles under the pack's
    formal environment, not unreachable at any depth. `timeout` is the whole
    call's budget. depth/input_changes/tb_text are None unless reachable.
    Raises UnsupportedCover, or RuntimeError when the tools themselves fail.
    """
    t0 = time.monotonic()
    pack = Path(pack_dir).resolve()
    label, target, top, staged = _prepare(pack, cover_file)
    out = {"label": label, "bound_module": target, "status": None, "depth": None,
           "input_changes": None, "input_changes_exact": None, "tb_text": None, "solve_s": None}

    with tempfile.TemporaryDirectory(prefix="cb-formal-") as d:
        work = Path(d)
        files = staged(work, prove=False)

        left = lambda: timeout - (time.monotonic() - t0)  # noqa: E731
        status, job = _sby(work, files, bound, left(), None)
        out["solve_s"] = round(time.monotonic() - t0, 1)
        if status == "ERROR":
            raise RuntimeError(f"sby failed:\n{_log_tail(job)}")
        if status in ("TIMEOUT",) or left() <= 0:
            return {**out, "status": "timeout", "total_s": round(time.monotonic() - t0, 1)}
        if status == "FAIL":
            return {**out, "status": "unreachable", "total_s": round(time.monotonic() - t0, 1)}
        best = _read_witness(job, top)
        depth = len(best)

        # Fewest input changes at that depth: binary search on a change budget.
        lo, hi, exact = 0, _changes(best), True
        while lo < hi:
            if left() <= 1:
                exact = False
                break
            mid = (lo + hi) // 2
            st, jb = _sby(work, files, depth, left(), mid)
            if st == "PASS":
                best, hi = _read_witness(jb, top), _changes(_read_witness(jb, top))
            elif st == "FAIL":
                lo = mid + 1
            elif st == "TIMEOUT":
                exact = False
                break
            else:
                raise RuntimeError(f"sby failed:\n{_log_tail(jb)}")
        return {**out, "status": "reachable", "depth": depth, "input_changes": _changes(best),
                "input_changes_exact": exact,
                "tb_text": witness_testbench(best, top, target, label),
                "total_s": round(time.monotonic() - t0, 1)}


def _prepare(pack: Path, cover_file: Path | str):
    """(label, bound module, formal.yaml top, staged(work, prove) -> files to read).

    staged writes the RTL (with the bind emulated), the translated cover and the env
    into work. prove=True turns the cover into `assert (!(e))` and reads no
    measurement wrapper: its change counter restricts long traces, so a proof
    through it would not cover every legal trace.
    """
    design = load_design(pack)
    spec = yaml.safe_load((pack / "formal" / "formal.yaml").read_text())["tops"]
    formal_text, binds = translate_cover(Path(cover_file).read_text())
    labels = re.findall(r"(\w+)\s*:\s*cover\s*\(", formal_text)
    if len(labels) != 1 or len(binds) != 1:
        raise ValueError(f"{cover_file}: expected exactly one cover and one bind, "
                         f"found {len(labels)} and {len(binds)}")
    target, instance = binds[0]
    if target not in spec:
        raise ValueError(f"no formal environment for module {target} in {pack}/formal/formal.yaml")
    top = spec[target]

    def staged(work: Path, *, prove: bool) -> list[str]:
        files = []
        for p in design.rtl:
            text = p.read_text()
            if re.search(rf"^\s*module\s+{target}\b", text, re.M):
                text = _insert_instance(text, target, instance)
            (work / p.name).write_text(text)
            files.append(p.name)
        text = formal_text
        if prove:
            m = re.search(rf"\b{labels[0]}\s*:\s*cover\s*\(", text)
            end = _balanced(text, m.end() - 1)
            text = (text[:m.start()] + f"{labels[0]}: assert (!({text[m.end():end - 1]}))"
                    + text[end:])
        (work / "cover.sv").write_text(text)
        shutil.copy(pack / "formal" / top["file"], work / "env.sv")
        files += ["cover.sv", "env.sv"]
        if not prove:
            (work / "measure.sv").write_text(_measure_wrapper(top))
            files.append("measure.sv")
        return files

    return labels[0], target, top, staged


PROVE_K = (1, 4, 16, 64)


def prove_unreachable(pack_dir: Path | str, cover_file: Path | str, *,
                      ks: tuple[int, ...] = PROVE_K, timeout: float = 600.0) -> dict:
    """k-induction proof that the cover never fires, under the pack's formal environment.

    Meant for a cover cover_witness reported unreachable within its bound. Returns
    {status: proven_unreachable | unreachable_within_bound | timeout, k, solve_s}:
    proven_unreachable when induction succeeds at some k in ks (k: the first that
    did); unreachable_within_bound when every k is inconclusive (an unreachable
    state can break induction without strengthening invariants); timeout when the
    budget ran out first. A proof holds relative to the environment's assumptions:
    a cover that contradicts an assumption (e.g. prescale outside the env range) is
    proven unreachable there, not in the design.
    Raises RuntimeError if a base case fails (the cover is reachable within k cycles:
    the caller's bounded result was wrong or used a smaller bound) or the tools fail.
    """
    t0 = time.monotonic()
    pack = Path(pack_dir).resolve()
    label, target, top, staged = _prepare(pack, cover_file)
    out = {"label": label, "bound_module": target, "k": None}
    with tempfile.TemporaryDirectory(prefix="cb-prove-") as d:
        work = Path(d)
        files = staged(work, prove=True)
        for k in ks:
            left = timeout - (time.monotonic() - t0)
            if left <= 1:
                break
            status, job = _sby(work, files, k, left, None, mode="prove", top=top["module"])
            if status == "PASS":
                return {**out, "status": "proven_unreachable", "k": k,
                        "solve_s": round(time.monotonic() - t0, 1)}
            if status == "FAIL":
                raise RuntimeError(f"{label}: base case fails at k={k}, the cover is reachable:\n"
                                   f"{_log_tail(job)}")
            if status == "TIMEOUT":
                break
            if status != "UNKNOWN":
                raise RuntimeError(f"sby failed:\n{_log_tail(job)}")
        else:
            return {**out, "status": "unreachable_within_bound",
                    "solve_s": round(time.monotonic() - t0, 1)}
    return {**out, "status": "timeout", "solve_s": round(time.monotonic() - t0, 1)}


def _log_tail(job: Path) -> str:
    log = job / "logfile.txt"
    return log.read_text()[-2000:] if log.exists() else "(no log)"
