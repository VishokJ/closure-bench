"""Deterministic citation checks for plan items.

RTL / README: the anchor string must appear on the cited lines of the pinned file.
DOC:          the document (from sources.yaml) must match its pinned SHA-256 and
              the anchor must appear on the cited page (whitespace-normalised).
BASE:         the cited coverage point must exist in the baseline with 0 hits.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from closure_core.coverage import CoverPoint

CACHE = Path.home() / ".cache" / "closure-bench" / "docs"


@dataclass
class CitationResult:
    item: str
    kind: str
    ok: bool | None      # None = could not be verified here (e.g. offline)
    detail: str


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def check_file_anchor(root: Path, item: str, src: dict) -> CitationResult:
    path = root / src["file"]
    lo, hi = src["lines"]
    lines = path.read_text(errors="replace").splitlines()[lo - 1:hi]
    found = _norm(src["anchor"]) in _norm(" ".join(lines))
    return CitationResult(item, src["type"], found,
                          f"{src['file']}:{lo}-{hi}" + ("" if found else f" lacks anchor {src['anchor']!r}"))


class DocStore:
    """Downloads cited documents, pins their hashes, extracts page text."""

    def __init__(self, pack: Path, offline: bool = False):
        self.registry = yaml.safe_load((pack / "sources.yaml").read_text())["documents"]
        self.lock_path = pack / "sources.lock"
        self.lock = json.loads(self.lock_path.read_text()) if self.lock_path.exists() else {}
        self.offline = offline
        self._pages: dict[str, list[str]] = {}

    def pages(self, doc_id: str) -> list[str]:
        if doc_id in self._pages:
            return self._pages[doc_id]
        meta = self.registry[doc_id]
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"{doc_id}.pdf"
        if not path.exists():
            if self.offline:
                raise ConnectionError("offline and not cached")
            req = urllib.request.Request(meta["url"], headers={"User-Agent": "closure-bench-check"})
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        pinned = self.lock.get(doc_id)
        if pinned is None:
            self.lock[doc_id] = digest  # trust on first use; review the lock file diff
            self.lock_path.write_text(json.dumps(self.lock, indent=2, sort_keys=True) + "\n")
        elif pinned != digest:
            raise ValueError(f"{doc_id}: SHA-256 {digest} does not match pinned {pinned}")
        from pypdf import PdfReader  # optional dependency: uv run --extra check
        self._pages[doc_id] = [p.extract_text() or "" for p in PdfReader(str(path)).pages]
        return self._pages[doc_id]


def check_doc(store: DocStore, item: str, src: dict) -> CitationResult:
    try:
        pages = store.pages(src["doc"])
    except (ConnectionError, OSError) as e:
        return CitationResult(item, "DOC", None, f"{src['doc']}: not verified ({e})")
    anchor = _norm(src["anchor"])
    found_on = [i + 1 for i, text in enumerate(pages) if anchor in _norm(text)]
    page = src.get("page")
    if page is None:
        return CitationResult(item, "DOC", False,
                              f"{src['doc']}: page not set; anchor found on pages {found_on or 'none'}"
                              + _snippets(pages, found_on, anchor))
    ok = page in found_on
    return CitationResult(item, "DOC", ok, f"{src['doc']} p.{page}" + (
        "" if ok else f": anchor {src['anchor']!r} not on page (found on {found_on or 'none'})"
        + _snippets(pages, found_on, anchor)))


def _snippets(pages: list[str], found_on: list[int], anchor: str, width: int = 80) -> str:
    """First match per page with some context, to help pick the right page."""
    out = []
    for p in found_on:
        text = _norm(pages[p - 1])
        i = text.index(anchor)
        out.append(f"\n    p.{p}: ...{text[max(0, i - width):i + len(anchor) + width]}...")
    return "".join(out)


def check_base(points: list[CoverPoint], item: str, src: dict) -> CitationResult:
    want = src["point"]
    match = [p for p in points
             if p.kind == want["kind"] and p.file.endswith("/" + want["file"])
             and p.line == want["line"] and p.name == want["name"]]
    if not match:
        return CitationResult(item, "BASE", False, f"no baseline point {want}")
    hits = sum(p.hits for p in match)
    return CitationResult(item, "BASE", hits == 0,
                          f"{want['file']}:{want['line']} {want['name']} has {hits} baseline hits")
