from check_module import check

DOC_REQ = {"type": "DOC", "role": "requirement", "doc": "pc16550d", "page": 16, "anchor": "x"}
RTL_REQ = {"type": "RTL", "role": "requirement", "file": "uart_rx.v", "lines": [126, 127], "anchor": "x"}
README_EV = {"type": "README", "file": "README.md", "lines": [42, 44], "anchor": "x"}


def test_kills_without_requirement_pass_as_mutant():
    assert check.value_gate(["m1"], [(README_EV, True)])[:2] == (True, "mutant")


def test_verified_doc_requirement_passes_as_spec():
    ok, evidence, spec = check.value_gate([], [(DOC_REQ, True)])
    assert (ok, evidence, spec) == (True, "spec", ["DOC pc16550d page 16"])


def test_unverified_requirement_does_not_count():
    assert check.value_gate([], [(DOC_REQ, False)])[:2] == (False, "none")
    assert check.value_gate([], [(DOC_REQ, None)])[:2] == (False, "none")  # e.g. --offline


def test_rtl_requirement_does_not_count():
    assert check.value_gate([], [(RTL_REQ, True)])[:2] == (False, "none")


def test_no_kills_no_requirement_fails():
    assert check.value_gate([], [(README_EV, True)]) == (False, "none", [])


def test_both():
    assert check.value_gate(["m1"], [(DOC_REQ, True)])[:2] == (True, "both")
