"""Cover and testbench policies on Verilator XML fixtures (tests/fixtures/policy).

The fixtures are Verilator 5.020 output; their version is recorded in
manifest.json. Regenerate inside the toolchain image:
    python3 tests/test_policy.py --regen
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from closure_core import policy  # noqa: E402

FIX = Path("tests/fixtures/policy")
RTL = "third_party/verilog-uart/rtl/uart_rx.v"

# case -> (item ID, substrings of the expected violations, one per violation)
COVER_CASES = {
    "ok_r1": ("R1", []),
    "ok_tracking": ("X", []),
    "ok_trivial": ("X", []),     # passes by design; baseline = 0 rejects it
    "ok_vacuous": ("X", []),     # passes by design; baseline = 0 rejects it
    "bad_initializer": ("X", ["initialstatic is not allowed"]),
    "bad_initial": ("X", ["initial is not allowed"]),
    "bad_display": ("X", ["display is not allowed"]),
    "bad_random": ("X", ["rand is not allowed"]),
    "bad_blocking": ("X", ["assign is not allowed"]),
    "bad_comb": ("X", ["contassign is not allowed"]),   # Verilator turns always_comb into assign
    "bad_level": ("X", ["without a clock edge"]),
    "bad_loop": ("X", ["assign is not allowed", "while is not allowed"]),
    "bad_hier_write": ("X", ["other than a local variable", "contassign is not allowed"]),
    "bad_hier_read": ("X", ["varxref is not allowed"]),
    "bad_output": ("X", ["'busy' is output", "other than a local variable"]),
    "bad_assert": ("X", ["not a cover property"]),
    "bad_shadow": ("X", ["exactly one module", "instance is not allowed"]),
    "bad_two_binds": ("X", ["exactly one bind", "as u_cov_X"]),
    "bad_bind_name": ("X", ["as u_cov_X"]),
    "bad_bind_ports": ("X", ["'frame_error' is not connected"]),
}
# case -> XML tags flagged
TB_CASES = {
    "tb_ok": [],
    # Verilator merges the adjacent $fdisplay and $fwrite into one display node.
    "tb_bad": ["assignforce", "release", "assign", "systemf", "systemt", "ucstmt", "ucfunc",
               "fopen", "display", "fgets", "fscanf", "fclose", "readmem", "writemem", "dumpctl"],
}
# case -> XML tags flagged by the gold policy (tb_ok is the real R1 gold)
GOLD_CASES = {
    "tb_ok": [],
    "gold_assert": ["assert", "stop"],   # assert only: inert in grading, and no $fatal
    "gold_no_fatal": ["stop"],
}
TESTBENCHES = sorted({*TB_CASES, *GOLD_CASES})


def _sources(case: str) -> list[str]:
    return [RTL, str(FIX / f"{case}.sv")]


def _ast(case: str) -> policy.Ast:
    return policy.Ast(ET.parse(ROOT / FIX / f"{case}.xml").getroot())


@pytest.mark.parametrize("case", COVER_CASES)
def test_cover_policy(case):
    item, expected = COVER_CASES[case]
    got = [str(v) for v in policy.check_cover(_ast(case), str(FIX / f"{case}.sv"), item, [RTL])]
    assert len(got) == len(expected), got
    for want in expected:
        assert any(want in g for g in got), (want, got)


@pytest.mark.parametrize("case", TB_CASES)
def test_testbench_policy(case):
    got = policy.check_testbench(_ast(case), str(FIX / f"{case}.sv"))
    assert sorted(v.construct for v in got) == sorted(TB_CASES[case]), [str(v) for v in got]


@pytest.mark.parametrize("case", GOLD_CASES)
def test_gold_policy(case):
    got = policy.check_gold(_ast(case), str(FIX / f"{case}.sv"))
    assert sorted(v.construct for v in got) == sorted(GOLD_CASES[case]), [str(v) for v in got]


def test_hierarchical_read_is_allowed_in_testbenches():
    got = policy.check_testbench(_ast("tb_bad"), str(FIX / "tb_bad.sv"))
    read_line = next(n for n, l in enumerate((ROOT / FIX / "tb_bad.sv").read_text().splitlines(), 1)
                     if "hierarchical read" in l)
    assert not [v for v in got if v.where.endswith(f":{read_line}")]


def test_r1_fixtures_are_the_real_files():
    assert (ROOT / FIX / "ok_r1.sv").read_text() == (ROOT / "designs/uart/covers/R1.sv").read_text()
    assert (ROOT / FIX / "tb_ok.sv").read_text() == (ROOT / "designs/uart/gold/R1.sv").read_text()


def _regenerate(case: str) -> str:
    extra = policy.TESTBENCH_FLAGS if case in TESTBENCHES else ()
    root, log = policy.xml_ast(_sources(case), extra=extra, cwd=ROOT)
    assert root is not None, f"{case}: verilator failed\n{log}"
    return ET.tostring(root, encoding="unicode")


def test_policy_refuses_other_verilator(monkeypatch):
    monkeypatch.setattr(policy, "verilator_version", lambda: "Verilator 5.052 2026-09-05")
    root, log = policy.xml_ast(_sources("ok_r1"), cwd=ROOT)
    assert root is None and "requires Verilator 5.020" in log


def test_manifest_matches_the_pin():
    manifest = json.loads((ROOT / FIX / "manifest.json").read_text())
    assert manifest["verilator"].startswith(policy.VERILATOR)
    assert list(policy.XML_FLAGS) == manifest["flags"]
    assert list(policy.TESTBENCH_FLAGS) == manifest["testbench_extra_flags"]


@pytest.mark.skipif(not policy.verilator_version().startswith(policy.VERILATOR),
                    reason="needs the pinned Verilator (toolchain image); the policy refuses others")
def test_fixtures_match_this_verilator():
    """A layout change in the pinned toolchain fails here instead of passing quietly."""
    manifest = json.loads((ROOT / FIX / "manifest.json").read_text())
    assert policy.verilator_version() == manifest["verilator"], "regenerate fixtures and review"
    for case in [*COVER_CASES, *TESTBENCHES]:
        assert _regenerate(case) == (ROOT / FIX / f"{case}.xml").read_text(), case


if __name__ == "__main__" and sys.argv[1:] == ["--regen"]:
    for case in [*COVER_CASES, *TESTBENCHES]:
        (ROOT / FIX / f"{case}.xml").write_text(_regenerate(case))
    (ROOT / FIX / "manifest.json").write_text(json.dumps(
        {"verilator": policy.verilator_version(), "flags": list(policy.XML_FLAGS),
         "testbench_extra_flags": list(policy.TESTBENCH_FLAGS), "rtl": [RTL]},
        indent=1) + "\n")
    print(f"regenerated {len(COVER_CASES) + len(TESTBENCHES)} fixtures with {policy.verilator_version()}")
