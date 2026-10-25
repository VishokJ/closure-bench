from closure_core import gates

DOC_REQ = {"type": "DOC", "role": "requirement", "doc": "pc16550d", "page": 16, "anchor": "x"}
RTL_REQ = {"type": "RTL", "role": "requirement", "file": "uart_rx.v", "lines": [126, 127], "anchor": "x"}
README_EV = {"type": "README", "file": "README.md", "lines": [42, 44], "anchor": "x"}


def value(kills, verified):
    r = gates.value(kills, [], verified)
    return r.ok, r.data["evidence"]


def test_kills_without_requirement_pass_as_mutant():
    assert value(["m1"], [(README_EV, True)]) == (True, "mutant")


def test_verified_doc_requirement_passes_as_spec():
    r = gates.value([], [], [(DOC_REQ, True)])
    assert (r.ok, r.data["evidence"], r.data["requirements"]) == (True, "spec", ["DOC pc16550d page 16"])


def test_unverified_requirement_does_not_count():
    assert value([], [(DOC_REQ, False)]) == (False, "none")
    assert value([], [(DOC_REQ, None)]) == (False, "none")  # e.g. --offline


def test_rtl_requirement_does_not_count():
    assert value([], [(RTL_REQ, True)]) == (False, "none")


def test_no_kills_no_requirement_fails():
    r = gates.value([], [], [(README_EV, True)])
    assert (r.ok, r.data["evidence"], r.data["requirements"]) == (False, "none", [])


def test_both():
    assert value(["m1"], [(DOC_REQ, True)]) == (True, "both")
