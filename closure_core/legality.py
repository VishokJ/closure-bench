"""Legal stimulus: the protocol and spec rules every testbench must obey.

designs/<name>/legality.yaml is the one source of truth, for two consumers:
  grader  checker_text(): one module chk_legal_<module> per design module with
          rules, bound to it and compiled with every graded testbench
          (grader.simulate). At an edge with a violation it prints
          `ILLEGAL_STIMULUS: <rule> at <time> in <instance>` per violated rule and
          calls $fatal; grader.simulate maps that to status illegal_stimulus.
  formal  assume_text(): the same conditions as assumptions, one module
          asm_legal_<module> per design module, instantiated inside it
          (closure_core/formal.py).

Both evaluate a rule on the values at a rising edge of clk: the checker in an
always @(posedge clk) block (the testbench drives on the falling edge, the
design's registers have not updated yet), formal at every step, which is one
rising edge. $past(p) becomes a register cb_past_p loaded at every edge, so it
means the same in both; rules with $past start at the second edge (cb_started).
Formal assumes combinationally (always @(*)), so the last step of a witness
obeys the rules too, and a witness testbench is legal by construction.

Allowed rules (a plan item's `legality: {allow: [...]}`) are left out of both
texts; enforced() decides which rules a grade enforces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

MARKER = "ILLEGAL_STIMULUS"
MARKER_RE = re.compile(rf"^{MARKER}: (\w+) at ", re.M)
CHECKER_FILE = "legality.sv"  # generated name, in the grader's work dir and in formal's

_PAST = re.compile(r"\$past\(\s*(\w+)\s*\)")
_LITERAL = re.compile(r"\d*'[sS]?[bodhBODH][0-9a-fA-F_xXzZ]+")
_IDENT = re.compile(r"(?<![\w$])[A-Za-z_]\w*")


@dataclass(frozen=True)
class Rule:
    id: str
    modules: tuple[str, ...]
    when: str
    require: str
    text: str
    sources: tuple[dict, ...]

    @property
    def uses_past(self) -> bool:
        return bool(_PAST.search(self.when + self.require))


@dataclass(frozen=True)
class Legality:
    ports: dict[str, dict[str, int]]  # module -> port -> width
    rules: tuple[Rule, ...]

    def rule(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(f"no legality rule {rule_id!r}")


NONE = Legality({}, ())


def load(path: Path) -> Legality:
    spec = yaml.safe_load(path.read_text()) or {}
    ports = {m: {p: int(w) for p, w in ps.items()} for m, ps in (spec.get("modules") or {}).items()}
    rules = tuple(Rule(id=r["id"], modules=tuple(r["modules"]), when=str(r.get("when", "1")),
                       require=str(r["require"]), text=" ".join(str(r["text"]).split()),
                       sources=tuple(r.get("sources") or ()))
                  for r in spec.get("rules") or ())
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate rule ids")
    for r in rules:
        for m in r.modules:
            if m not in ports:
                raise ValueError(f"{path}: rule {r.id}: module {m} has no ports entry")
            unknown = sorted(set(_names(r.when) + _names(r.require)) - set(ports[m]))
            if unknown or "clk" not in ports[m]:
                raise ValueError(f"{path}: rule {r.id}: {unknown or ['clk']} not among the ports of {m}")
        if not r.sources:
            raise ValueError(f"{path}: rule {r.id} cites no source")
    return Legality(ports, rules)


def _names(expr: str) -> list[str]:
    return _IDENT.findall(_LITERAL.sub("", expr))


def enforced(legality: Legality, allows: list[tuple[str, ...]]) -> tuple[Rule, ...]:
    """Rules a grade enforces: allows holds each target's allowed rule ids, and a rule is
    dropped only if every target allows it. A multi-target task or a campaign never
    gets easier than its strictest target was measured; a hazard item grouped with
    others is held to the rule it is about (a reported limitation)."""
    dropped = set.intersection(*map(set, allows)) if allows else set()
    return tuple(r for r in legality.rules if r.id not in dropped)


def _expr(e: str) -> str:
    return _PAST.sub(lambda m: f"cb_past_{m.group(1)}", e)


def _module_parts(legality: Legality, rules: tuple[Rule, ...], module: str):
    """(port declarations, past registers, rules) for one module; None if it has no rules."""
    mine = [r for r in rules if module in r.modules]
    if not mine:
        return None
    ports = legality.ports[module]
    used = {"clk", *(n for r in mine for n in _names(r.when) + _names(r.require))}
    past = sorted({n for r in mine for n in _PAST.findall(r.when + r.require)})
    decl = [f"{'[' + str(ports[n] - 1) + ':0] ' if ports[n] > 1 else ''}{n}" for n in ports if n in used]
    return decl, [(n, ports[n]) for n in past], mine


def _vec(w: int) -> str:
    return f"[{w - 1}:0] " if w > 1 else ""


def checker_text(legality: Legality, rules: tuple[Rule, ...], source: str = "legality.yaml") -> str:
    """The simulation checker for `rules`: modules plus binds; empty if no module has a rule."""
    out = []
    for module in legality.ports:
        parts = _module_parts(legality, rules, module)
        if parts is None:
            continue
        decl, past, mine = parts
        lines = [f"// Generated by closure_core/legality.py from {source}; checks inputs only.",
                 f"module chk_legal_{module} (",
                 ",\n".join(f"  input logic {d}" for d in decl), ");",
                 "  logic cb_started = 1'b0;",
                 "  logic cb_bad;",
                 *(f"  logic {_vec(w)}cb_past_{n} = '0;" for n, w in past),
                 "  always @(posedge clk) begin",
                 "    cb_bad = 1'b0;"]
        for r in mine:
            guard = "cb_started && " if r.uses_past else ""
            lines += [f"    if ({guard}({_expr(r.when)}) && !({_expr(r.require)})) begin",
                      f'      $display("{MARKER}: {r.id} at %0t in %m", $time);',
                      "      cb_bad = 1'b1;",
                      "    end"]
        lines += ["    if (cb_bad) $fatal(1, \"illegal stimulus\");",
                  "    cb_started <= 1'b1;",
                  *(f"    cb_past_{n} <= {n};" for n, _ in past),
                  "  end",
                  "endmodule",
                  f"bind {module} chk_legal_{module} u_chk_legal (.*);", ""]
        out.append("\n".join(lines))
    return "\n".join(out)


def assume_text(legality: Legality, rules: tuple[Rule, ...]) -> dict[str, str]:
    """Formal: design module -> (module text of asm_legal_<module>, instance text to
    insert into that module). Only modules with a rule."""
    out = {}
    for module in legality.ports:
        parts = _module_parts(legality, rules, module)
        if parts is None:
            continue
        decl, past, mine = parts
        lines = ["// Generated by closure_core/legality.py from legality.yaml: legal stimulus.",
                 f"module asm_legal_{module} (",
                 ",\n".join(f"  input wire {d}" for d in decl), ");",
                 "  reg cb_started = 1'b0;",
                 "  always @(posedge clk) cb_started <= 1'b1;",
                 *(f"  reg {_vec(w)}cb_past_{n} = {w}'d0;\n  always @(posedge clk) cb_past_{n} <= {n};"
                   for n, w in past)]
        for r in mine:
            guard = "cb_started && " if r.uses_past else ""
            lines.append(f"  always @(*) if ({guard}({_expr(r.when)})) {r.id}: assume ({_expr(r.require)});")
        lines += ["endmodule", ""]
        out[module] = ("\n".join(lines), f"asm_legal_{module} u_asm_legal (.*);")
    return out


def violations(run_log: str) -> list[str]:
    """Rule ids the checker reported in a run log, in order."""
    return MARKER_RE.findall(run_log)


def prompt_lines(rules: tuple[Rule, ...]) -> list[str]:
    """One line per rule for the agent prompt: id, modules, text, the exact condition, source."""
    def cite(s: dict) -> str:
        if s["type"] == "DOC":
            return f"{s['doc']}" + (f" s{s['section']}" if s.get("section") else "") + f", p.{s['page']}"
        return f"{Path(s['file']).name} lines {s['lines'][0]}-{s['lines'][1]}"
    return [f"{r.id} ({', '.join(r.modules)}): {r.text} Violated when `{r.when}` and not "
            f"`{r.require}`. Source: {'; '.join(cite(s) for s in r.sources)}."
            for r in rules]
