"""Campaign finalize: what reaches the grader from submission/ (fake runtime).

The real listing is `find -type f` (no symlinks, GNU -printf); here its output
is canned, so this checks the parsing, selection, rewrite and reply fallback.
"""

import asyncio
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("verifiers")
from closure_bench.taskset import ClosureBenchTaskset, ClosureConfig  # noqa: E402


class FakeRuntime:
    def __init__(self, listing: dict[str, bytes]):
        self.listing = listing   # what find reports as regular files in submission/
        self.cmds, self.written = [], {}

    async def run(self, cmd, env):
        self.cmds.append(cmd)
        if cmd[0] == "find":
            out = "".join(f"{len(d)} {n}\0" for n, d in self.listing.items())
            return NS(exit_code=0, stdout=out, stderr="")
        return NS(exit_code=0, stdout="", stderr="")

    async def read(self, path, max_bytes):
        return self.listing[path.rsplit("/", 1)[1]][:max_bytes]

    async def write(self, path, data):
        self.written[path] = data


def _finalize(listing, reply="", max_files=None):
    task = ClosureBenchTaskset(ClosureConfig(tasks="campaign", max_files=max_files)).load()[0]
    rt, trace = FakeRuntime(listing), NS(last_reply=reply, info={})
    asyncio.run(task.finalize(trace, rt))
    return rt, trace


def test_keeps_matching_files_and_rewrites_dir():
    listing = {f"tb_{i}.sv": b"module tb; endmodule\n" for i in range(10)}
    listing |= {"tb.sv": b"x", "notes.txt": b"x", "tb_0_blank.sv": b"  \n",
                "tb_big.sv": b"x" * 1_000_001, "tb_a b.sv": b"x"}
    rt, trace = _finalize(listing, max_files=8)
    # tb_0_blank.sv sorts second but is blank: dropped before the cap, no slot taken.
    kept = [f"tb_{i}.sv" for i in range(8)]
    assert sorted(trace.info["submission"]) == kept
    assert trace.info["submission_source"] == "file"
    assert ["rm", "-rf", "/workspace/submission"] in rt.cmds
    assert sorted(rt.written) == [f"/workspace/submission/{n}" for n in kept]


def test_falls_back_to_reply_blocks():
    reply = "```systemverilog\nmodule tb; endmodule\n```\n```sv\nmodule tb; endmodule\n```"
    rt, trace = _finalize({}, reply)
    assert sorted(trace.info["submission"]) == ["tb_1.sv", "tb_2.sv"]
    assert trace.info["submission_source"] == "reply"


def test_default_cap_is_one_file_per_target():
    listing = {f"tb_{i:02d}.sv": b"module tb; endmodule\n" for i in range(15)}
    rt, trace = _finalize(listing)   # task 0: uart_rx, 11 targets
    assert len(trace.info["submission"]) == 11


def test_empty_submission():
    rt, trace = _finalize({})
    assert (trace.info["submission"], trace.info["submission_source"], rt.written) == ({}, "none", {})
    assert ["mkdir", "-p", "/workspace/submission"] in rt.cmds  # the artifact dir still exists
