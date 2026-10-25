from pathlib import Path

from closure_core import mutants
from closure_core.design import find_repo_root

ROOT = find_repo_root()
RX = ROOT / "third_party/verilog-uart/rtl/uart_rx.v"


def gen(src: str, tmp_path: Path) -> list[mutants.Mutant]:
    f = tmp_path / "m.v"
    f.write_text("module m;\n" + src + "\nendmodule\n")
    return mutants.generate(f, 1, src.count("\n") + 3)


def test_deterministic():
    assert mutants.generate(RX, 86, 140) == mutants.generate(RX, 86, 140)


def test_ids_unique():
    ms = mutants.generate(RX, 86, 140)
    assert len({m.id for m in ms}) == len(ms)


def test_each_mutant_changes_exactly_one_line():
    text = RX.read_text()
    for m in mutants.generate(RX, 86, 140):
        before, after = text.splitlines(), mutants.apply(text, m).splitlines()
        assert len(before) == len(after)
        changed = [i + 1 for i, (a, b) in enumerate(zip(before, after)) if a != b]
        assert changed == [m.line], m.id


def test_relational_swaps_only_inside_if_conditions(tmp_path):
    ms = gen("x <= y;\nif (a <= b) z <= 1;", tmp_path)
    rel = [m for m in ms if m.op in mutants.REL_OPS]
    assert [(m.line, m.op) for m in rel] == [(3, "le_lt")]
    assert rel[0].mutated == "if (a < b) z <= 1;"


def test_shifts_are_not_relational(tmp_path):
    ms = gen("if ((p << 3) > 0) q <= 0;", tmp_path)
    rel = [m for m in ms if m.op in mutants.REL_OPS]
    assert [m.mutated for m in rel] == ["if ((p << 3) >= 0) q <= 0;"]


def test_stuck_skips_noop(tmp_path):
    ops = {m.op for m in gen("x <= 0;", tmp_path)}
    assert "stuck0" not in ops and "stuck1" in ops


def test_concat_lhs_is_an_assignment(tmp_path):
    ops = {m.op for m in gen("{a, b} <= {1'b0, c};", tmp_path)}
    assert {"stuck0", "stuck1", "drop"} <= ops


def test_comments_are_not_mutated(tmp_path):
    assert gen("// if (a == b) x <= 1;", tmp_path) == []


def test_r1_frame_error_stuck0_exists():
    m = {m.id: m for m in mutants.generate(RX, 86, 140)}["uart_rx.v:127:stuck0:0"]
    assert m.module == "uart_rx"
    assert m.mutated.strip() == "frame_error_reg <= 0;"


def test_no_duplicate_mutants():
    ms = mutants.generate(RX, 86, 140)
    assert len({(m.line, m.mutated) for m in ms}) == len(ms)


def test_cache_key_includes_platform(monkeypatch):
    monkeypatch.setattr(mutants, "_toolchain", lambda: "Verilator 5.020")
    rtl = {RX: RX.read_text()}
    key = lambda: mutants.cache_key(rtl, "module tb; endmodule", "tb", 20.0)
    base = key()
    monkeypatch.setattr(mutants.platform, "machine", lambda: "other-arch")
    assert key() != base
