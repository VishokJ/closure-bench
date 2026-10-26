"""tools/failure_analysis: one test per layer-1 rule, each on a diagnostic string taken
from the hard2 official traces; event divergence; pass@k; Cohen's kappa; the blind
handcheck sample; residual labels recorded and replayed with no model call."""

from __future__ import annotations

import csv
import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_loader = importlib.machinery.SourceFileLoader("failure_analysis", str(ROOT / "tools" / "failure_analysis"))
_spec = importlib.util.spec_from_loader("failure_analysis", _loader)
fa = importlib.util.module_from_spec(_spec)
_loader.exec_module(fa)

PORTS = {"uart": ["clk", "rst", "s_axis_tdata", "s_axis_tvalid", "s_axis_tready", "m_axis_tdata", "m_axis_tvalid",
                  "m_axis_tready", "rxd", "txd", "tx_busy", "rx_busy", "rx_overrun_error", "rx_frame_error",
                  "prescale"],
         "uart_rx": ["clk", "rst", "m_axis_tdata", "m_axis_tvalid", "m_axis_tready", "rxd", "busy",
                     "overrun_error", "frame_error", "prescale"]}


def rollout(status="compile_error", diag="", submission="module tb; endmodule\n", *, reward=0.0, finish="stop",
            grade=True, reply="", reasoning="", key="m/R1/0", **grade_kw):
    g = {"status": status, "reward": reward, "diagnostics": diag, "target_hits": {"R1": 0},
         "plan_hits": {"R1": 0}, "run_s": 1.0, **grade_kw} if grade else None
    return {"key": key, "model": key.split("/")[0], "task": key.split("/")[1], "design": "uart",
            "targets": [key.split("/")[1]], "grade": g, "submission": submission, "finish_reasons": [finish],
            "stop_condition": "agent_completed" if grade else "provider_error", "is_timeout": False,
            "errors": [] if grade else ["upstream stream ended before its terminal event"],
            "output_tokens": 1000, "max_tokens": 65536, "reply": reply, "reasoning": reasoning,
            "submission_source": "reply", "line": 1, "traces": "t.jsonl", "run": "run", "image": "img",
            "run_timeout": 60.0}


def lines_at(n: int, text: str) -> str:
    """A submission whose line n is text."""
    return "\n" * (n - 1) + text + "\n"


def classify(*a, **kw):
    return fa.classify(rollout(*a, **kw), PORTS)


# --- layer 1: one test per rule, real diagnostics ------------------------------------------------

def test_infra_no_grade():
    lab = classify(grade=False)
    assert lab["category"] == "infra" and lab["sub_label"] == "no_grade"
    assert lab["evidence"]["stop_condition"] == "provider_error"


def test_infra_verilator_internal_error():
    d = ("%Error: Internal Error: <work>/submission/tb.sv:109:17: ../V3Ast.h:2359: AstNode is not of expected "
         "type, but instead has type 'IF'")
    lab = classify(diag=d)
    assert (lab["category"], lab["sub_label"]) == ("infra", "verilator_internal")
    assert "V3Ast.h:2359" in lab["evidence"]["diagnostic"]


def test_budget_max_tokens():
    d = "%Error: Specified --top-module 'tb' was not found in design.\n%Error: Exiting due to 1 error(s)"
    lab = classify(diag=d, submission="", finish="length")
    assert (lab["category"], lab["sub_label"]) == ("budget", "max_tokens")
    assert lab["evidence"]["finish_reason"] == "length"


@pytest.mark.parametrize("reply,reasoning,sub", [
    ("", "Let me draft it.\nmodule tb;\n  initial $finish;\nendmodule\n", "answer_in_reasoning"),
    ("", "I think the overrun needs two frames.", "no_answer"),
    # Nemotron R22: a doubled opening fence leaves the last code block empty.
    ("```systemverilog\n```systemverilog\nmodule tb;\nendmodule\n```", "", "malformed_fence"),
])
def test_empty_answer(reply, reasoning, sub):
    d = "%Error: Specified --top-module 'tb' was not found in design."
    lab = classify(diag=d, submission="\n", reply=reply, reasoning=reasoning)
    assert (lab["category"], lab["sub_label"]) == ("empty_answer", sub)
    assert lab["evidence"]["finish_reason"] == "stop"


def test_answer_testbench_takes_the_last_tb():
    prompt = fa._prompt_module()
    text = "draft:\nmodule tb; // v1\nendmodule\nthen\n```systemverilog\nmodule tb; // v2\nendmodule\n```\nok"
    assert "v2" in fa.answer_testbench(text, prompt)
    assert "v1" in fa.answer_testbench("module tb; // v1\nendmodule", prompt)


def test_literal_bitselect():
    d = "%Error: <work>/submission/tb.sv:54:18: syntax error, unexpected '[', expecting ';'"
    lab = classify(diag=d, submission=lines_at(54, "      rxd = 8'hA5[i];"))
    assert lab["category"] == "literal_bitselect"
    assert lab["evidence"]["literal"].startswith("8'hA5[")


def test_unexpected_bracket_without_literal_is_other_syntax():
    d = "%Error: <work>/submission/tb.sv:54:18: syntax error, unexpected '[', expecting ';'"
    assert classify(diag=d, submission=lines_at(54, "x = y [i];"))["category"] == "other_syntax"


@pytest.mark.parametrize("diag,sub", [
    ("%Error-UNSUPPORTED: <work>/submission/tb.sv:61:13: Unsupported: Unclocked assertion",
     "Unsupported: Unclocked assertion"),
    ("%Error: <work>/submission/tb.sv:60:18: syntax error, unexpected void", "void cast"),
    ("%Error-BLKANDNBLK: <work>/submission/tb.sv:71:7: Unsupported: Blocked and non-blocking assignments to "
     "same variable: 'tb.timer_cnt'", "Unsupported: Blocked and non-blocking assignments to same variable: '…'"),
])
def test_unsupported_construct(diag, sub):
    lab = classify(diag=diag)
    assert (lab["category"], lab["sub_label"]) == ("unsupported_construct", sub)


def test_undeclared():
    d = "%Error: <work>/submission/tb.sv:44:11: Can't find definition of variable: 'busy'"
    lab = classify(diag=d)
    assert (lab["category"], lab["sub_label"]) == ("undeclared", "busy")


def test_assign_to_input():
    d = "%Error-ASSIGNIN: <work>/submission/tb.sv:31:18: Assigning to input/const variable: 'prescale'"
    lab = classify(diag=d)
    assert (lab["category"], lab["sub_label"]) == ("assign_to_input", "prescale")


def test_include_path():
    d = "%Error: <work>/submission/tb.sv:2:10: Cannot find include file: rtl/uart_rx.v"
    lab = classify(diag=d)
    assert (lab["category"], lab["sub_label"]) == ("include_path", "rtl/uart_rx.v")


def test_interface_hallucination_records_pin_and_real_ports():
    d = ("%Warning-PINMISSING: <work>/submission/tb.sv:33:26: Cell has missing pin: 'tx_busy'\n"
         "%Error-PINNOTFOUND: <work>/submission/tb.sv:43:6: Pin not found: 'busy'\n"
         "%Error: Exiting due to 1 error(s)")
    sub = lines_at(33, "  uart #(.DATA_WIDTH(8)) dut (") + "\n" * 8 + "    .busy (),\n"
    lab = classify(diag=d, submission=sub)
    assert (lab["category"], lab["sub_label"]) == ("interface_hallucination", "busy")
    ev = lab["evidence"]
    assert ev["module"] == "uart" and "rx_busy" in ev["real_ports"] and "busy" not in ev["real_ports"]
    assert ev["pinmissing"] == ["tx_busy"]


def test_pinmissing_alone_does_not_decide():
    """PINMISSING is a warning (-Wno-fatal): the first fatal error decides."""
    d = ("%Warning-PINMISSING: <work>/submission/tb.sv:62:26: Cell has missing pin: 'm_axis_tdata'\n"
         "%Error: <work>/submission/tb.sv:59:8: Duplicate declaration of signal: 'tx_busy_dummy'")
    lab = classify(diag=d)
    assert lab["category"] == "other_syntax"
    assert lab["evidence"]["pinmissing"] == ["m_axis_tdata"]


def test_parameter_not_found_is_interface_hallucination():
    d = "%Error-PINNOTFOUND: <work>/submission/tb.sv:118:14: Parameter not found: 'PRESCALE'"
    lab = classify(diag=d)
    assert (lab["category"], lab["sub_label"], lab["evidence"]["kind"]) == (
        "interface_hallucination", "PRESCALE", "parameter")


def test_other_syntax_keeps_first_error_and_sub_labels():
    d = ("%Error: <work>/submission/tb.sv:85:9: syntax error, unexpected IDENTIFIER, expecting \"'{\"\n"
         "%Error-PINNOTFOUND: <work>/submission/tb.sv:90:6: Pin not found: 'busy'")
    lab = classify(diag=d, submission=lines_at(85, "    int bit_clks = prescale * 8;"))
    assert (lab["category"], lab["sub_label"]) == ("other_syntax", "decl_after_statement")
    assert lab["evidence"]["diagnostic"].startswith("%Error: <work>/submission/tb.sv:85:9")
    assert lab["evidence"]["categories_in_log"] == {"other_syntax": 1, "interface_hallucination": 1}
    d = "%Error: Specified --top-module 'tb' was not found in design.\n%Error: Exiting due to 1 error(s)"
    assert classify(diag=d)["sub_label"] == "top_module_missing"


@pytest.mark.parametrize("status", ["timeout", "no_finish"])
def test_never_finishes(status):
    lab = classify(status, "ERROR: simulation stopped without $finish")
    assert (lab["category"], lab["sub_label"]) == ("never_finishes", status)


def test_self_check_failed():
    d = ("[668000] %Fatal: tb.sv:98: Assertion failed in TOP.tb: First byte is not 0xA5 (got 00)\n"
         "%Error: <work>/submission/tb.sv:98: Verilog $stop")
    lab = classify("runtime_error", d)
    assert (lab["category"], lab["sub_label"]) == ("self_check_failed", "check")
    assert lab["evidence"]["diagnostic"].startswith("Assertion failed in TOP.tb: First byte")
    d = ("[10000000000] %Fatal: tb.sv:116: Assertion failed in TOP.tb: timeout\n"
         "%Error: <work>/submission/tb.sv:116: Verilog $stop")
    assert classify("runtime_error", d)["sub_label"] == "watchdog"


def test_runtime_crash_is_not_a_self_check():
    """Nemotron R17/5: `forever #0` crashes with only the compile log (warnings on tb.sv) left."""
    d = ("%Warning-INITIALDLY: <work>/submission/tb.sv:81:19: Non-blocking assignment '<=' in initial/final block\n"
         "make: Leaving directory '<work>/build'\n")
    assert classify("runtime_error", d)["category"] == "runtime_crash"


def test_illegal_stimulus_rule():
    d = ("ILLEGAL_STIMULUS: axis_tvalid_held at 6476000 in TOP.tb.dut.uart_tx_inst.u_chk_legal\n"
         "%Error: <work>/legal/legality.sv:70: Verilog $stop")
    lab = classify("illegal_stimulus", d)
    assert (lab["category"], lab["sub_label"]) == ("illegal_stimulus", "axis_tvalid_held")
    assert lab["evidence"]["time"] == 6476000


def test_policy_violation():
    d = "<work>/submission/tb.sv:141: file I/O (waveform dump) is not allowed in a testbench"
    lab = classify("policy_violation", d)
    assert (lab["category"], lab["sub_label"]) == (
        "policy_violation", "file I/O (waveform dump) is not allowed in a testbench")


def test_miss():
    lab = classify("ok", "", plan_hits={"R1": 0, "R3": 2})
    assert lab["category"] == "miss" and lab["evidence"]["other_items_hit"] == ["R3"]


# --- layer 2 ---------------------------------------------------------------------------------

def test_monitor_binds_the_design_not_the_testbench():
    text = fa.monitor_text("/x/events.log")
    assert "bind uart_rx cb_fa_mon_rx" in text and "bind uart_tx cb_fa_mon_tx" in text
    assert "bind tb" not in text and '$fopen("/x/events.log"' in text


def test_first_divergence():
    gold = fa.parse_events("1 15000 rx prescale 1\n154 1545000 rx overrun_error 1\n230 2305000 rx overrun_error 1\n")
    same = fa.parse_events("1 9 rx prescale 1\n154 9 rx overrun_error 1\n230 9 rx overrun_error 1\n")
    assert fa.first_divergence(gold, same) is None
    shifted = fa.parse_events("1 9 rx prescale 1\n160 9 rx overrun_error 1\n400 9 rx overrun_error 1\n")
    d = fa.first_divergence(gold, shifted)
    assert (d["index"], d["reason"], d["submission_cycles"]) == (0, "at a different cycle", [160, 400])
    assert d["sequence"] is None  # same events in order, other cycles
    once = fa.parse_events("1 9 rx prescale 5\n154 9 rx overrun_error 1\n")
    d = fa.first_divergence(gold, once)  # prescale is compared apart, never the divergence
    assert (d["index"], d["reason"]) == (1, "at a different cycle")
    assert d["sequence"]["index"] == 1 and d["prescale"] == {"gold": [1], "submission": [5]}
    other = fa.parse_events("1 9 rx prescale 5\n")
    assert fa.first_divergence(gold, other)["reason"] == "missing"


# --- layers 3 to 6 -----------------------------------------------------------------------------

def test_pass_at_k_unbiased():
    assert fa.pass_at_k(8, 0, 1) == 0.0 and fa.pass_at_k(8, 8, 8) == 1.0
    assert fa.pass_at_k(8, 2, 1) == pytest.approx(0.25)
    assert fa.pass_at_k(8, 1, 8) == 1.0
    assert fa.pass_at_k(8, 1, 2) == pytest.approx(1 - 21 / 28)


def test_cohen_kappa():
    assert fa.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert fa.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert fa.cohen_kappa(["a"] * 3, ["a"] * 3) == 1.0


def test_parse_label():
    assert fa.parse_label('{"label": "wrong_data", "reason": "sub `236 ... rx hs 3c`"}') == (
        "wrong_data", "sub `236 ... rx hs 3c`")
    assert fa.parse_label("I think wrong data")[0] == "unclear"
    assert fa.parse_label('{"label": "made_up", "reason": "x"}')[0] == "unclear"


def _failed(n_models=2, per=30):
    rs, labels = [], {}
    cats = ["miss", "literal_bitselect", "never_finishes"]
    for m in range(n_models):
        for i in range(per if m == 0 else 3):
            r = rollout(key=f"m{m}/R{i % 5}/{i}")
            rs.append(r)
            labels[r["key"]] = {"category": cats[i % 3], "sub_label": None, "evidence": {"x": i}, "logs": {}}
    return rs, labels


def test_handcheck_is_stratified_blind_and_deterministic():
    rs, labels = _failed()
    rows, key_map = fa.handcheck_rows(rs, labels, {})
    again, _ = fa.handcheck_rows(rs, labels, {})
    assert rows == again
    strata = [s for v in key_map.values() for s in v["strata"]]
    assert sum(s == "category:literal_bitselect" for s in strata) == 5
    # m1 has 2 residuals (< RESIDUAL_MIN): all of them; the sample comes from m0 only.
    assert sum(s == "residual:all_of_small_model" for s in strata) == 2
    assert sum(s == "residual:sample" for s in strata) == 20
    assert all(v["key"].startswith("m0/") for v in key_map.values() if "residual:sample" in v["strata"])
    for row in rows:  # blind: no predicted label anywhere in the row
        assert row["hand_category"] == "" and "category" not in row and "stratum" not in row


def test_agreement(tmp_path):
    rs, labels = _failed()
    for k, lab in labels.items():
        if lab["category"] in fa.RESIDUAL_SET:
            lab["residual"] = {"label": "wrong_data"}
    rows, key_map = fa.handcheck_rows(rs, labels, {})
    for row in rows:
        lab = labels[row["rollout"]]
        row["hand_category"] = lab["category"]
        row["hand_residual_label"] = "wrong_data"
    p = tmp_path / "handcheck.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    a = fa.agreement(p, labels, key_map)
    assert a["precision"]["literal_bitselect"]["precision"] == 1.0
    assert a["residual"]["accuracy"] == 1.0 and a["residual"]["validated"]


def test_residual_labels_recorded_and_replayed(tmp_path):
    from closure_core.propose import ScriptedModel
    r = rollout("ok", key="m0/R1/0")
    msgs = [{"role": "user", "content": "label this"}]
    model = ScriptedModel(['{"label": "near_miss", "reason": "sub `233 ... rx overrun_error 1`"}'])
    got = fa.label_residuals(tmp_path, [(r, {}, msgs)], model, 1)
    assert got == {"m0/R1/0": ("near_miss", "sub `233 ... rx overrun_error 1`")}
    rec = json.loads((tmp_path / "labels" / "m0__R1__0.json").read_text())
    assert rec["messages"] == msgs and rec["params"]["model"] == "scripted"
    assert fa.label_residuals(tmp_path, [(r, {}, msgs)], fa.NoModel(), 1) == got  # replay: no call
    with pytest.raises(RuntimeError):  # a changed prompt cannot reuse the recorded answer
        fa.label_residuals(tmp_path, [(r, {}, [{"role": "user", "content": "other"}])], fa.NoModel(), 1)


def test_pass_at_k_keeps_tasks_with_fewer_rollouts():
    # n < k falls back to pass@n: a 0/7 task counts as 0, a 5/7 task as 1, never dropped
    assert fa.pass_at_k_all(7, 0, 8) == 0.0
    assert fa.pass_at_k_all(7, 5, 8) == 1.0
    assert fa.pass_at_k_all(8, 2, 1) == pytest.approx(0.25)
