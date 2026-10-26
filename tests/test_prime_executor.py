"""PrimeExecutor against a fake runtime: a local directory plays the sandbox.

The protocol tests stub gate_candidate inside the fake sandbox (no simulator):
what is uploaded, what comes back, what is never overwritten, and how sandbox
failures map to InfraError. The determinism test runs the real gate_candidate
in the fake sandbox and locally on the same gold-less candidate (canned
witness) and needs the pinned Verilator (toolchain image).
"""

import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
import types
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from closure_core import propose
from closure_core.infra import InfraError
from closure_core.prime_executor import DOCS, MUTATION_CACHE, ROOT_IN_SANDBOX, PrimeExecutor

from test_formal_gate import WITNESS, add_formal_env, seed, stimulus
from test_gate_candidate import ROOT, empty_pack, needs_sim, r1_candidate


@pytest.fixture
def scratch():
    d = ROOT / "results" / "tmp" / f"test_prime_{uuid.uuid4().hex[:8]}"  # inside the repo: tools need it
    yield d
    shutil.rmtree(d, ignore_errors=True)


class FakeSandbox:
    """provision() for PrimeExecutor: each call is a fresh empty directory under `base`,
    standing in for the sandbox's /repo. tool(root, argv) -> (exit, stdout, stderr)
    replaces tools/gate_candidate if given; every other command runs for real there."""

    def __init__(self, base: Path, tool=None, fail_creates: int = 0):
        self.base, self.tool, self.fail_creates = base, tool, fail_creates
        self.created = self.active = self.max_active = 0
        self.lock = threading.Lock()

    @asynccontextmanager
    async def __call__(self):
        with self.lock:
            self.created += 1
            n = self.created
            if n <= self.fail_creates:
                raise RuntimeError("sandbox create failed")
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        root = self.base / f"sbx{n}"
        root.mkdir(parents=True)
        try:
            yield FakeRuntime(root, self.tool)
        finally:
            with self.lock:
                self.active -= 1
            shutil.rmtree(root)


class FakeRuntime:
    """The sandbox's ROOT_IN_SANDBOX is this directory; the working directory is too."""

    def __init__(self, root: Path, tool):
        self.root, self.tool = root, tool

    def _map(self, s: str) -> str:
        return s.replace(ROOT_IN_SANDBOX, str(self.root))

    async def write(self, path: str, data: bytes) -> None:
        Path(self._map(path)).parent.mkdir(parents=True, exist_ok=True)
        Path(self._map(path)).write_bytes(data)

    async def read(self, path: str) -> bytes:
        return Path(self._map(path)).read_bytes()

    async def run(self, argv: list[str], env: dict) -> types.SimpleNamespace:
        if self.tool and argv[0] == "tools/gate_candidate":
            code, out, err = await asyncio.to_thread(self.tool, self.root, argv)
        else:
            p = await asyncio.to_thread(subprocess.run, [self._map(a) for a in argv], cwd=self.root,
                                        env={**os.environ, **{k: self._map(v) for k, v in env.items()}},
                                        capture_output=True, text=True)
            code, out, err = p.returncode, p.stdout, p.stderr
        return types.SimpleNamespace(exit_code=code, stdout=out, stderr=err)


def executor(sandbox: FakeSandbox, tmp: Path, **kw) -> PrimeExecutor:
    return PrimeExecutor(concurrency=kw.pop("concurrency", 2), provision=sandbox,
                         mutation_cache=tmp / "mutation_cache.json", docs=tmp / "docs", **kw)


def setup_run(scratch: Path):
    """A candidate, a base pack and a witness cache with one entry, as a run has them."""
    cand = r1_candidate(scratch / "candidates" / "c01" / "0")
    base = empty_pack(scratch / "base_pack")
    wc = scratch / "formal"
    wc.mkdir(parents=True)
    (wc / "old.json").write_text('{"status": "unreachable"}\n')
    (wc / ".formal.lock").write_text("")
    return cand, base, wc


def stub_tool(seen: dict):
    """Records what the sandbox had, then writes a result, a new witness, a changed old
    witness and a new mutation-cache entry."""
    def tool(root: Path, argv: list[str]):
        rel = lambda flag: root / argv[argv.index(flag) + 1]  # noqa: E731
        seen["files"] = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
        mc = root / MUTATION_CACHE
        seen["mutation"] = json.loads(mc.read_text()) if mc.exists() else {}
        mc.parent.mkdir(parents=True, exist_ok=True)
        (rel("--witness-cache") / "new.json").write_text('{"status": "reachable"}\n')
        (rel("--witness-cache") / "old.json").write_text('{"status": "changed in the sandbox"}\n')
        (root / MUTATION_CACHE).write_text(json.dumps({**seen["mutation"], "k2": {"status": "ok"}}))
        rel("--out").parent.mkdir(parents=True, exist_ok=True)
        rel("--out").write_text(json.dumps({"accepted": True, "item": "P1"}))
        return 0, "ACCEPTED", ""
    return tool


def test_round_trip(scratch, tmp_path):
    cand, base, wc = setup_run(scratch)
    (tmp_path / "mutation_cache.json").write_text(json.dumps({"k1": {"status": "ok"}}))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "pc16550d.pdf").write_bytes(b"%PDF")
    seen = {}
    sbx = FakeSandbox(tmp_path / "sbx", stub_tool(seen))
    ex = executor(sbx, tmp_path)
    out = scratch / "gates" / "c01" / "0.json"
    res = ex.gate(cand, out, base, {"cache": wc, "min_frames": None, "require_mechanism": False})

    assert res == {"accepted": True, "item": "P1"} and json.loads(out.read_text()) == res
    rel = lambda p: str(p.relative_to(ROOT))  # noqa: E731
    files = seen["files"]
    assert f"{rel(cand)}/gold.sv" in files and f"{rel(base)}/design.yaml" in files
    assert f"{rel(wc)}/old.json" in files and f"{rel(wc)}/.formal.lock" not in files
    assert f"{DOCS}/pc16550d.pdf" in files and "closure_core/gates.py" in files
    assert "third_party/verilog-uart/rtl/uart_rx.v" in files and "tools/gate_candidate" in files
    assert not any("__pycache__" in f for f in files)
    assert seen["mutation"] == {"k1": {"status": "ok"}}
    # New witness downloaded; an existing one is never overwritten; mutation entries merged.
    assert json.loads((wc / "new.json").read_text()) == {"status": "reachable"}
    assert json.loads((wc / "old.json").read_text()) == {"status": "unreachable"}
    assert json.loads((tmp_path / "mutation_cache.json").read_text()) == {"k1": {"status": "ok"}, "k2": {"status": "ok"}}
    assert sbx.created == 1 and sbx.active == 0  # torn down
    assert ex.calls[0]["exit"] == 0 and ex.calls[0]["upload_bytes"] > 0


def test_tools_stay_executable(scratch, tmp_path):
    """The real tool scripts run from their shebang in the sandbox (modes survive the upload)."""
    seen = {}

    def tool(root, argv):
        seen["x"] = os.access(root / "tools" / "gate_candidate", os.X_OK)
        return 1, "", ""

    cand, base, wc = setup_run(scratch)
    with pytest.raises(RuntimeError, match="gate_candidate failed"):  # exit 1 without a result: not infra
        executor(FakeSandbox(tmp_path / "sbx", tool), tmp_path).gate(cand, scratch / "o.json", base)
    assert seen["x"]


def test_exit_2_is_infra_and_not_retried(scratch, tmp_path):
    cand, base, _ = setup_run(scratch)
    sbx = FakeSandbox(tmp_path / "sbx", lambda root, argv: (2, "", "INFRASTRUCTURE ERROR: sim timed out twice"))
    out = scratch / "gates" / "c01" / "0.json"
    with pytest.raises(InfraError, match="timed out twice"):
        executor(sbx, tmp_path).gate(cand, out, base)
    assert not out.exists() and sbx.created == 1  # the tool already retried its own timeouts


def test_sandbox_failure_is_retried_once(scratch, tmp_path):
    cand, base, _ = setup_run(scratch)
    ok = stub_tool({})
    wc = scratch / "formal"
    formal = {"cache": wc, "min_frames": None, "require_mechanism": False}
    sbx = FakeSandbox(tmp_path / "a", ok, fail_creates=1)
    assert executor(sbx, tmp_path).gate(cand, scratch / "a.json", base, formal)["accepted"]
    assert sbx.created == 2

    sbx = FakeSandbox(tmp_path / "b", ok, fail_creates=2)
    with pytest.raises(InfraError, match="failed twice"):
        executor(sbx, tmp_path).gate(cand, scratch / "b.json", base, formal)
    assert sbx.created == 2 and not (scratch / "b.json").exists()


def test_timeout_is_infra(scratch, tmp_path):
    cand, base, _ = setup_run(scratch)
    sbx = FakeSandbox(tmp_path / "sbx", lambda root, argv: (time.sleep(1), (0, "", ""))[1])
    with pytest.raises(InfraError, match="TimeoutError"):
        executor(sbx, tmp_path, timeout=0.2).gate(cand, scratch / "o.json", base)
    assert sbx.created == 2 and sbx.active == 0 and not (scratch / "o.json").exists()


def test_concurrency_limit(scratch, tmp_path):
    cand, base, _ = setup_run(scratch)

    def slow(root, argv):
        time.sleep(0.3)
        out = root / argv[argv.index("--out") + 1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("{}")
        return 0, "", ""

    sbx = FakeSandbox(tmp_path / "sbx", slow)
    ex = executor(sbx, tmp_path, concurrency=2)
    threads = [threading.Thread(target=ex.gate, args=(cand, scratch / f"o{n}.json", base)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sbx.created == 5 and sbx.max_active == 2


def test_network_off_before_upload(monkeypatch):
    """The real provisioner: a Prime config with no egress, and set_network before any write."""
    rt_mod = pytest.importorskip("verifiers.v1.runtimes")
    events = []

    class Rt:
        async def set_network(self, net):
            events.append(("network", list(net.allow), list(net.block)))

    @asynccontextmanager
    async def provision_runtime(cfg):
        events.append(("create", cfg.image, list(cfg.allow), cfg.workdir))
        yield Rt()

    monkeypatch.setattr(rt_mod, "provision_runtime", provision_runtime)

    async def go():
        async with PrimeExecutor(concurrency=1)._prime():
            events.append(("upload",))

    asyncio.run(go())
    assert events == [("create", propose.IMAGE, [], "/repo"), ("network", [], ["*"]), ("upload",)]


def test_record_executor(scratch):
    scratch.mkdir(parents=True)
    propose.record_executor(scratch, "c01", "0", propose.Executor(image=None))  # no manifest: a replay, ignored
    assert not (scratch / "manifest.json").exists()
    propose.dump(scratch / "manifest.json", {"run_id": "x"})
    propose.record_executor(scratch, "c01", "0", propose.Executor(image=None))
    propose.record_executor(scratch, "c01", "set", PrimeExecutor(concurrency=1, provision=FakeSandbox(scratch)))
    assert propose.load(scratch / "manifest.json")["executors"] == {
        "c01": {"0": "local", "set": f"prime:{propose.IMAGE}"}}


@needs_sim
def test_same_gates_json_as_local(scratch, tmp_path):
    """A gold-less R1 through the formal gate (canned witness), gated locally and in
    the fake sandbox: identical gates.json."""
    cand = r1_candidate(scratch / "candidates" / "c01" / "0")
    (cand / "gold.sv").unlink()
    base = add_formal_env(empty_pack(scratch / "base_pack"))
    for name in ("local", "prime"):
        seed(scratch / f"formal_{name}", base, cand, {"P1_frame_error": {**WITNESS, "tb_text": stimulus()}})
    shared = ROOT / MUTATION_CACHE
    if shared.exists():
        shutil.copy(shared, tmp_path / "mutation_cache.json")
    opts = lambda n: {"cache": scratch / f"formal_{n}", "min_frames": None, "require_mechanism": False}  # noqa: E731
    local = propose.Executor(image=None, j=2).gate(cand, scratch / "local.json", base, opts("local"))
    prime = executor(FakeSandbox(tmp_path / "sbx"), tmp_path).gate(cand, scratch / "prime.json", base,
                                                                    opts("prime"))
    assert local["accepted"], local
    assert prime == local


def test_missing_verifiers_fails_at_once(monkeypatch):
    """No retry, no sandbox: the host is not set up."""
    import builtins
    real = builtins.__import__

    def no_verifiers(name, *a, **kw):
        if name.startswith("verifiers"):
            raise ImportError(f"No module named {name!r}")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_verifiers)
    with pytest.raises(ImportError, match="activate the venv"):
        PrimeExecutor(concurrency=1)
