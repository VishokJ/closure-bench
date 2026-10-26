"""DOC anchors: compared with all whitespace removed, case-sensitive, on exactly one page."""

import types

import pytest

from closure_core import citations
from closure_core.design import find_repo_root

PACK = find_repo_root() / "designs" / "uart"


def store(*pages):
    return types.SimpleNamespace(pages=lambda doc: list(pages))


def check(anchor, page, *pages):
    return citations.check_doc(store(*pages), "P1", {"doc": "d", "page": page, "anchor": anchor})


def test_whitespace_is_ignored_both_ways():
    assert check("The UART will try to resynchronize", 1, "TheUART will try to\nresynchronize after").ok
    assert check("Framing Error", 1, "Fram ing\n  Error (FE)").ok


def test_case_still_counts():
    r = check("the uart will try", 1, "TheUART will try")
    assert r.ok is False and "not on page (found on none)" in r.detail


def test_exactly_one_page():
    r = check("Framing Error", 2, "Framing Error", "Framing  Error, bit 3")
    assert r.ok is False and "is on pages [1, 2]" in r.detail and "only on p.2" in r.detail
    r = check("Framing Error, bit 3", 2, "Framing Error", "Framing  Error, bit 3")
    assert r.ok is True and r.detail == "d p.2"


def test_wrong_page_shows_where_it_is():
    r = check("resynchronize", 1, "nothing here", "TheUART will try to resynchronize after")
    assert r.ok is False and "found on [2]" in r.detail
    assert "p.2: ...TheUART will try to resynchronize after..." in r.detail  # readable context


def test_smoke_c02_anchor_on_the_datasheet():
    """The anchor a smoke run lost at citations: pypdf extracts "TheUART will try ..." on p.16."""
    if not (citations.CACHE / "pc16550d.pdf").exists():
        pytest.skip("pc16550d.pdf not in the doc cache")
    s = citations.DocStore(PACK, offline=True)
    r = citations.check_doc(s, "P2", {"doc": "pc16550d", "page": 16,
                                      "anchor": "The UART will try to resynchronize after a framing error."})
    assert r.ok is True, r.detail
