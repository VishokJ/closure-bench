"""AST policy checks on Verilator's own parse (verilator --xml-only), not regex.

One walker, two policies:

  cover      allowlist for our cover files (covers/<ID>.sv). Accepted covers
             are grader code: they run inside every future grading run, so a
             cover may only observe. Allowed: input ports, parameter/localparam,
             local tracking registers written with non-blocking assignments in
             clocked always blocks (if/case/begin only), cover property, and
             sampled-value functions. Everything else is rejected: initial
             blocks and initializers, blocking or continuous assignments,
             combinational always, loops, every system task or function
             ($random would make coverage nondeterministic), hierarchical
             references, assertions, instances, outputs. Exactly one module,
             cov_<ID>, and exactly one bind, `bind <RTL module> cov_<ID>
             u_cov_<ID>`, with every port connected to the same-named signal
             (what `.*` does; coverage.plan_hits assumes this placement).

  testbench  denylist of dangerous constructs in testbenches, enforced by
             grader.grade() before simulating (status policy_violation):
             force/release, $system, $c, file I/O, hierarchical writes into
             the design, any instance placed inside a module the testbench
             does not define (bind; a bound module can drive a design
             register through an output port), and redefining a design or
             cover module, and any parameter override on a design module
             (#() or defparam, at any depth) that changes a value: covers are
             bound without parameters and may assume the defaults. Verilator
             compiles an override as a renamed copy (uart_rx__D9, origName
             uart_rx), so that is what is checked; an override equal to the
             default makes no copy and passes. Testbenches are legitimately
             rich, so only listed constructs are rejected; hierarchical reads
             are allowed. Our own golds and
             near-misses get the same denylist; checking golds also may not
             use assert/assume (inert without --assert) and must call $fatal
             (check_gold). Reach golds (formal witnesses) get the denylist
             only: they reach the behaviour and check nothing.

Verilator keeps the first definition of a module and drops later ones from
the XML, so parse_testbench puts the testbench first: a redefinition is then
the definition that survives, and is visible.

The XML is Verilator 5.020's lowered AST. A cover property appears as a named
begin holding a clocked always whose if-body has a coverinc; each $past,
$rose, $fell or $stable appears as a generated clocked always that assigns a
local _Vpast_* register from `sampled`. The cover allowlist is written against
that form, so generated and hand-written tracking logic obey the same rule.
Widen the allowlist only when a real candidate needs a construct, with a test.
The XML layout is version-specific: tests/fixtures/policy records the version
and a test regenerates the fixtures whenever Verilator is available.

What the cover policy does not catch, by design: a cover that is trivially or
vacuously true, e.g. `cover property (@(posedge clk) 1)`, or `a |-> b`, which
is hit on every cycle where a is low. The policy is about what a cover may
do; whether it is hit too easily is the baseline gate's job (baseline = 0).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# Only user coverage: line/toggle coverage would add instrumentation nodes.
XML_FLAGS = ("--xml-only", "--coverage-user", "--timing", "-Wno-fatal", "--prefix", "Vtop")
# Testbenches are parsed with --assert added (policy only; grading never uses
# it): without it Verilator drops immediate assertions from the AST entirely,
# so an inert-assert gold would be invisible.
TESTBENCH_FLAGS = ("--assert",)
# The XML layout is version-specific: refuse any other Verilator rather than
# check an AST the policy was not written for.
VERILATOR = "Verilator 5.020 "

COVER_STATEMENTS = {"var", "always", "sentree", "senitem", "begin", "if", "case", "caseitem",
                    "assigndly", "coverinc", "coverdecl"}
# Pure expression nodes seen in accepted covers (tests/fixtures/policy).
COVER_EXPRESSIONS = {"varref", "const", "sampled", "not", "and", "or", "xor", "redor", "redand",
                     "eq", "neq", "add", "sub", "sel", "cond", "extend", "concat",
                     # Every relational form (ok_compare): which one a comparison lowers to
                     # depends on constant folding and operand order, not on what was written.
                     "lt", "lte", "gt", "gte", "lts", "ltes", "gts", "gtes", "extends"}
COVER_ALLOWED = COVER_STATEMENTS | COVER_EXPRESSIONS

TESTBENCH_DENIED = {
    "assignforce": "force", "release": "release",
    "systemf": "$system", "systemt": "$system",
    "ucstmt": "$c", "ucfunc": "$c",
    "fopen": "file I/O", "fclose": "file I/O", "readmem": "file I/O", "writemem": "file I/O",
    "fscanf": "file I/O", "fgets": "file I/O", "dumpctl": "file I/O (waveform dump)",
}
FILE_DISPLAY = {"$fdisplay", "$fwrite", "$fstrobe", "$fmonitor"}
ASSIGNMENTS = {"assign", "assigndly", "contassign", "assignforce"}


@dataclass(frozen=True)
class Violation:
    where: str      # file:line
    construct: str  # XML tag
    reason: str

    def __str__(self) -> str:
        return f"{self.where}: {self.reason}"


def verilator_version() -> str:
    try:
        return subprocess.run(["verilator", "--version"], capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        return "none"


def xml_ast(sources: list[Path | str], *, extra: tuple[str, ...] = (), cwd: Path | None = None,
            timeout: float = 60.0) -> tuple[ET.Element | None, str]:
    """Verilator's XML for these sources: (root, "") or (None, log).

    File names in the XML are the strings passed here, verbatim.
    """
    version = verilator_version()
    if not version.startswith(VERILATOR):
        return None, f"policy requires {VERILATOR.strip()} (its XML layout is version-specific); found {version!r}"
    with tempfile.TemporaryDirectory(prefix="cb-xml-") as d:
        p = subprocess.run(["verilator", *XML_FLAGS, *extra, "--Mdir", d, *map(str, sources)],
                           cwd=cwd, capture_output=True, text=True, timeout=timeout)
        xml = Path(d) / "Vtop.xml"
        if p.returncode != 0 or not xml.exists():
            return None, (p.stdout + p.stderr)[-4000:]
        return ET.parse(xml).getroot(), ""


class Ast:
    """Lookups over one parsed XML netlist."""

    def __init__(self, root: ET.Element):
        self.root = root
        self.files = {f.get("id"): f.get("filename") for f in root.find("files")}
        self.modules = list(root.iter("module"))

    def file_of(self, node: ET.Element) -> str:
        return self.files.get((node.get("loc") or "?").split(",")[0], "?")

    def where(self, node: ET.Element) -> str:
        loc = (node.get("loc") or "?,?").split(",")
        return f"{self.files.get(loc[0], '?')}:{loc[1] if len(loc) > 1 else '?'}"

    def defined_in(self, filename: str) -> list[ET.Element]:
        return [m for m in self.modules if self.file_of(m) == filename]


def walk(ast: Ast, module: ET.Element, check) -> list[Violation]:
    """Visit every node under module; check(node, parents) returns a reason or None.

    A rejected node's subtree is not visited further (one report per construct).
    """
    out: list[Violation] = []

    def visit(node: ET.Element, parents: tuple[ET.Element, ...]) -> None:
        reason = check(node, parents)
        if reason:
            out.append(Violation(ast.where(node), node.tag, reason))
            return
        for c in node:
            visit(c, parents + (node,))

    for c in module:
        visit(c, (module,))
    return out


def _cover_check(module: ET.Element):
    vars_ = [v for v in module if v.tag == "var"]
    local = {v.get("name") for v in vars_
             if v.get("dir") is None and not (v.get("param") or v.get("localparam"))}

    def check(node: ET.Element, parents: tuple[ET.Element, ...]) -> str | None:
        tag, parent = node.tag, parents[-1]
        if tag not in COVER_ALLOWED:
            return f"{tag} is not allowed in a cover module"
        if tag == "var" and node.get("dir") not in (None, "input"):
            return f"port {node.get('name')!r} is {node.get('dir')} (inputs only)"
        if tag == "always":
            edges = [s.get("edgeType") for s in node.iter("senitem")]
            if node.find("sentree") is None or not edges or not set(edges) <= {"POS", "NEG"}:
                return "always block without a clock edge (combinational logic is not allowed)"
        if tag == "begin" and parent is module and node.find(".//coverinc") is None:
            return f"named block {node.get('name')!r} is not a cover property (assert/assume?)"
        if tag == "assigndly":
            target = node[-1]
            if target.tag != "varref" or target.get("name") not in local:
                return "non-blocking assignment to something other than a local variable"
        return None

    return check


def check_cover(ast: Ast, cover_file: str, item_id: str, rtl_files: list[str]) -> list[Violation]:
    """Cover policy for one cover file; file names as they appear in the XML."""
    name, inst = f"cov_{item_id}", f"u_cov_{item_id}"
    out: list[Violation] = []
    mods = ast.defined_in(cover_file)
    if [m.get("name") for m in mods] != [name]:
        out.append(Violation(cover_file, "module",
                             f"must define exactly one module, {name}; defines {[m.get('name') for m in mods]}"))
    for m in mods:
        out += walk(ast, m, _cover_check(m))

    binds = [(m, i) for m in ast.modules for i in m.iter("instance") if ast.file_of(i) == cover_file]
    binds = [(m, i) for m, i in binds if m.get("name") not in {x.get("name") for x in mods}]
    if len(binds) != 1:
        out.append(Violation(cover_file, "bind", f"must contain exactly one bind; found {len(binds)}"))
    for target, i in binds:
        where = ast.where(i)
        if i.get("defName") != name or i.get("name") != inst:
            out.append(Violation(where, "bind", f"bind must instantiate {name} as {inst}; "
                                                f"got {i.get('defName')} {i.get('name')}"))
        if ast.file_of(target) not in rtl_files:
            out.append(Violation(where, "bind", f"bind target {target.get('name')} is not a design module"))
        for p in i.iter("port"):
            conn = [c for c in p if c.tag == "varref"]
            if len(conn) != 1 or conn[0].get("name") != p.get("name"):
                out.append(Violation(where, "bind", f"port {p.get('name')!r} is not connected to the "
                                                    f"same-named signal (use .*)"))
    return out


MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.M)


def module_names(paths: list[Path]) -> set[str]:
    """Modules defined in our own files (RTL, covers): the names a testbench may not reuse."""
    return {n for p in paths for n in MODULE_RE.findall(Path(p).read_text())}


def parse_testbench(tb: Path | str, ours: list[Path | str], *, extra: tuple[str, ...] = (),
                    cwd: Path | None = None) -> tuple[ET.Element | None, str]:
    """xml_ast with the testbench first, so its redefinitions are the ones kept."""
    return xml_ast([tb, *ours], extra=extra, cwd=cwd)


# Constants a description may name: sized or based Verilog literals and 0x hex.
# Plain decimals ("prescale 5", "19 clocks") are ignored: too often stimulus or prose.
DESC_LITERAL = re.compile(r"(?<![\w'])(\d*)'[sS]?([hHdDbBoO])([0-9a-fA-F_]+)\b|\b0[xX]([0-9a-fA-F_]+)\b")
DESC_IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
BASES = {"h": 16, "d": 10, "b": 2, "o": 8}


def literal_value(text: str) -> int | None:
    """Value of a Verilog literal as Verilator writes it in the XML (8'ha5, 32'sh3); None if not one."""
    m = re.fullmatch(r"\d*'s?([hdbo])([0-9a-fA-F_]+)", text.strip(), re.I)
    return int(m.group(2).replace("_", ""), BASES[m.group(1).lower()]) if m else None


def description_refs(description: str, signals: set[str]) -> tuple[list[str], dict[str, int]]:
    """(design signal names, {literal text: value}) a plan description mentions."""
    names = sorted({w for w in DESC_IDENT.findall(description) if w in signals})
    lits = {}
    for m in DESC_LITERAL.finditer(description):
        digits, base = (m.group(3), m.group(2).lower()) if m.group(2) else (m.group(4), "h")
        lits[m.group(0)] = int(digits.replace("_", ""), BASES[base])
    return names, lits


def check_description(ast: Ast, cover_file: str, item_id: str, rtl_files: list[str],
                      description: str) -> list[str]:
    """Names and constants the description mentions that the cover never reads.

    A design signal counts only if the cover reads it through an input port of
    the same name (connected by .* to that signal); a declared port that is
    never read does not count, nor does a local register that shares a name.
    A constant counts if a const with that value appears in the cover module.
    """
    cover = next((m for m in ast.defined_in(cover_file) if m.get("name") == f"cov_{item_id}"), None)
    targets = {m.get("name") for m in ast.modules if ast.file_of(m) in rtl_files
               for i in m.iter("instance") if ast.file_of(i) == cover_file}
    signals = {v.get("name") for m in ast.modules if m.get("name") in targets
               for v in m if v.tag == "var" and not (v.get("param") or v.get("localparam"))}
    names, lits = description_refs(description, signals)
    if cover is None:
        return [*names, *lits]
    inputs = {v.get("name") for v in cover if v.tag == "var" and v.get("dir") == "input"}
    read = {n.get("name") for n in cover.iter("varref")} & inputs
    values = {literal_value(c.get("name") or "") for c in cover.iter("const")}
    return [n for n in names if n not in read] + [t for t, v in lits.items() if v not in values]


def _testbench_check(node: ET.Element, parents: tuple[ET.Element, ...]) -> str | None:
    tag = node.tag
    if tag in TESTBENCH_DENIED:
        return f"{TESTBENCH_DENIED[tag]} is not allowed in a testbench"
    if tag == "display" and node.get("displaytype") in FILE_DISPLAY:
        return f"file I/O ({node.get('displaytype')}) is not allowed in a testbench"
    # The assignment target is the last child; reads of design internals are allowed.
    x = next(node[-1].iter("varxref"), None) if tag in ASSIGNMENTS and len(node) else None
    if x is not None:
        return f"hierarchical write into the design ({x.get('dotted')}.{x.get('name')})"
    return None


def check_testbench(ast: Ast, tb_file: str, reserved: set[str] = frozenset()) -> list[Violation]:
    """Testbench denylist over every module defined in tb_file.

    reserved: module names defined in our files (module_names); needs XML from
    parse_testbench, else a redefinition is dropped before we can see it.
    """
    mods = ast.defined_in(tb_file)
    out = [Violation(ast.where(m), "module", f"redefines design or cover module {m.get('name')!r}")
           for m in mods if m.get("name") in reserved]
    out += [v for m in mods for v in walk(ast, m, _testbench_check)]
    names = {m.get("name") for m in mods}
    out += [Violation(ast.where(i), "bind", f"instance {i.get('name')!r} ({i.get('defName')}) placed inside "
                                            f"module {m.get('name')!r} (bind is not allowed in a testbench)")
            for m in ast.modules if m.get("name") not in names
            for i in m.iter("instance") if ast.file_of(i) == tb_file]
    # Parameter overrides: a specialised copy of one of our modules.
    special = {m.get("name"): m.get("origName") for m in ast.modules
               if m.get("origName") in reserved and m.get("name") != m.get("origName")}
    flagged = [i for m in mods for i in m.iter("instance") if i.get("defName") in special]
    out += [Violation(ast.where(i), "parameter", f"instance {i.get('name')!r} overrides a parameter of "
                                                 f"{special[i.get('defName')]!r}; use the default parameters")
            for i in flagged]
    if special and not flagged:  # e.g. a defparam reaching an instance inside the design
        out.append(Violation(tb_file, "parameter", f"parameters of {sorted(set(special.values()))} are overridden; "
                                                   f"use the default parameters"))
    return out


def check_gold(ast: Ast, tb_file: str, reserved: set[str] = frozenset(), *,
               role: str = "checking") -> list[Violation]:
    """Our gold testbenches. role "checking": the denylist, no assertions, and at
    least one $fatal; role "reach" (a formal witness): the denylist only.

    The grader compiles without --assert, so an assertion never fires and a
    gold relying on one can never fail. Needs XML parsed with TESTBENCH_FLAGS,
    where every assertion is an `if` guarded by a cexpr (assertOn()).
    """
    if role not in ("checking", "reach"):
        raise ValueError(f"unknown gold role {role!r}")
    mods = ast.defined_in(tb_file)
    out = check_testbench(ast, tb_file, reserved)
    if role == "reach":
        return out
    # One report per source line: `assert ... else $error` guards both parts.
    lines = dict.fromkeys(ast.where(n) for m in mods for n in m.iter("if") if len(n) and n[0].tag == "cexpr")
    out += [Violation(w, "assert", "assert/assume never fires in grading (no --assert); use if (...) $fatal")
            for w in lines]
    fatal = any("%Fatal:" in (f.get("name") or "") for m in mods for f in m.iter("sformatf"))
    if not fatal:
        out.append(Violation(tb_file, "stop", "a gold must call $fatal when the behaviour is wrong"))
    return out
