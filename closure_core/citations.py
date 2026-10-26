"""Deterministic citation checks for plan items.

RTL / README: the anchor string must appear on the cited lines of the pinned file.
DOC:          the document (from sources.yaml) must match its pinned SHA-256 and
              the anchor must appear on the cited page and on no other, compared
              with all whitespace removed (PDF extraction drops and adds spaces:
              "TheUART will try") but case-sensitive.
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


def _squash(s: str) -> tuple[str, list[int]]:
    """s without whitespace, and each kept character's index in s."""
    keep = [i for i, c in enumerate(s) if not c.isspace()]
    return "".join(s[i] for i in keep), keep


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
    anchor, _ = _squash(src["anchor"])
    found_on = [i + 1 for i, text in enumerate(pages) if anchor and anchor in _squash(text)[0]]
    page = src.get("page")
    if page is None:
        return CitationResult(item, "DOC", False,
                              f"{src['doc']}: page not set; anchor found on pages {found_on or 'none'}"
                              + _snippets(pages, found_on, anchor))
    if found_on == [page]:
        return CitationResult(item, "DOC", True, f"{src['doc']} p.{page}")
    if page in found_on:
        why = f"anchor {src['anchor']!r} is on pages {found_on}; quote a longer passage that is only on p.{page}"
    else:
        why = f"anchor {src['anchor']!r} not on page (found on {found_on or 'none'})"
    return CitationResult(item, "DOC", False, f"{src['doc']} p.{page}: {why}" + _snippets(pages, found_on, anchor))


def _snippets(pages: list[str], found_on: list[int], anchor: str, width: int = 80) -> str:
    """First match per page with some context (as extracted, whitespace collapsed),
    to help pick the right page. anchor: whitespace already removed."""
    out = []
    for p in found_on:
        text = pages[p - 1]
        squashed, pos = _squash(text)
        i = squashed.index(anchor)
        lo, hi = pos[i], pos[i + len(anchor) - 1] + 1
        snip = re.sub(r"\s+", " ", text[max(0, lo - width):hi + width]).strip()
        out.append(f"\n    p.{p}: ...{snip}...")
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
