"""Gate runs in Prime sandboxes: one fresh sandbox per call, so a proposer run
can gate many candidates at once instead of on local Docker.

PrimeExecutor overrides only Executor.run: gate(), context_pack() and check()
are inherited, so the tools get the same arguments as with the local executor.
Each call:

  create   a sandbox from the pipeline image, then networking off
  upload   one tarball: the repo code (closure_core, tools, designs, third_party
           from the working tree), every run path the argv names (candidate,
           base pack, the run's witness cache), the shared mutation cache and
           witness store (gates.MUTATION_CACHE, gates.witness_store) and the cited
           PDFs (the sandbox cannot download them)
  run      the argv, from the repo root at ROOT_IN_SANDBOX (/repo, as in Docker)
  download the --out file, new witness-cache entries, new mutation-cache and
           witness-store entries, into the local files the set stage and replay
           read and the shared caches (merged, never overwriting an entry)
  teardown always

The whole witness cache is uploaded, not just the entries for this candidate's
covers: a key includes `yosys -V`, which the host cannot compute, and entries
are a few KB. Entries are immutable: a download never overwrites a local one.

A sandbox failure (create, upload, run, download, timeout) is retried once in a
fresh sandbox, then raises InfraError: never a rejection, never cached
(closure_core/infra.py). Exit code 2 from the tool is an infrastructure error
too; Executor.gate raises it, as for the local executor (the tool has already
retried its own timeouts). The formal-timeout lock (gates.formal_slot) is per
sandbox: one solve per sandbox is never contended.

Needs the verifiers package (its Prime runtime) and Prime credentials; imported
lazily, so closure_core itself stays free of verifiers.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from closure_core import gates
from closure_core.infra import InfraError
from closure_core.propose import IMAGE, ROOT, Executor

ROOT_IN_SANDBOX = "/repo"
CODE = ("closure_core", "tools", "designs", "third_party")
# Under the sandbox repo root; HOME is set to match, so these are gates.CACHE_DIR there.
MUTATION_CACHE = ".home/.cache/closure-bench/mutation_cache.json"
WITNESSES = ".home/.cache/closure-bench/witnesses"
DOCS = ".home/.cache/closure-bench/docs"
SKIP = ("__pycache__", ".formal.lock")
CPU, MEMORY_GB, DISK_GB = 4, 8, 10
RUN_TIMEOUT = 3600.0  # gate_candidate wall clock; the formal budget alone is up to 2 x 900 s


def _skip(p: Path) -> bool:
    return any(part in SKIP for part in p.parts) or p.suffix == ".pyc"


def _flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def _require_verifiers() -> None:
    try:
        import verifiers.v1.runtimes  # noqa: F401
    except ImportError as e:
        raise ImportError(f"the prime executor needs the verifiers package ({e}): activate the venv "
                          f"(source .venv/bin/activate)") from e


class PrimeExecutor(Executor):
    """Executor whose tools run in Prime sandboxes, at most `concurrency` at once."""

    def __init__(self, image: str = IMAGE, concurrency: int = 8, *, cpu: int = CPU, memory: float = MEMORY_GB,
                 disk: float = DISK_GB, timeout: float = RUN_TIMEOUT, provision=None,
                 mutation_cache: Path | None = None, witness_store: Path | None = None, docs: Path | None = None,
                 root: str = ROOT_IN_SANDBOX):
        """provision: async context manager factory yielding a runtime (write/run/read);
        default a Prime sandbox. Tests pass a fake, with `root` a local directory."""
        if provision is None:
            _require_verifiers()
        super().__init__(image, j=cpu)
        self.concurrency, self.cpu, self.memory, self.disk, self.timeout = concurrency, cpu, memory, disk, timeout
        self.provision = provision or self._prime
        self.mutation_cache = mutation_cache or gates.MUTATION_CACHE
        self.witness_store = witness_store or gates.witness_store()
        # The sandbox's store for the same formal.py (uploaded from this working tree).
        store = gates.witness_store(Path(WITNESSES))
        self.store_arc = str(store) if store else None
        self.docs = docs or Path.home() / ".cache" / "closure-bench" / "docs"
        self.root = root
        self.calls: list[dict] = []  # per call: seconds per phase, sizes, image_cached, machine
        self._slots = threading.BoundedSemaphore(concurrency)
        self._merge = threading.Lock()

    @property
    def label(self) -> str:
        return f"prime:{self.image}"

    @asynccontextmanager
    async def _prime(self):
        from verifiers.v1.runtimes import NetworkPolicyConfig, PrimeConfig, provision_runtime
        cfg = PrimeConfig(image=self.image, workdir=self.root, cpu=self.cpu, memory=self.memory, disk=self.disk,
                          allow=[], labels=["closure-bench-gate"])
        async with provision_runtime(cfg) as rt:
            # Model-written SystemVerilog runs here: networking off before anything is uploaded.
            await rt.set_network(NetworkPolicyConfig(allow=[]))
            yield rt

    def run(self, argv: list[str]) -> subprocess.CompletedProcess:
        errors = []
        with self._slots:
            for attempt in range(2):
                try:
                    return asyncio.run(self._session(argv))
                except ImportError:
                    raise  # a missing package is the host's setup, not the sandbox: retrying cannot help
                except Exception as e:  # noqa: BLE001 - every failure here is the sandbox's, not the candidate's
                    errors.append(f"attempt {attempt}: {type(e).__name__}: {e}")
                    print(f"prime: {argv[0]} sandbox failed ({errors[-1][:300]})", file=sys.stderr, flush=True)
        raise InfraError("prime sandbox failed twice; treating it as infrastructure, not as a decision:\n"
                         + "\n".join(e[-1000:] for e in errors))

    def _upload(self, argv: list[str]) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            paths = [ROOT / c for c in CODE]
            # Run inputs the argv names (candidate, base pack, witness cache); outputs do not exist yet.
            paths += [ROOT / a for a in argv[1:] if not a.startswith("-") and (ROOT / a).exists()
                      and Path(a).parts[0] not in CODE]
            for p in paths:
                tar.add(p, arcname=str(p.relative_to(ROOT)), filter=lambda t: None if _skip(Path(t.name)) else t)
            if self.mutation_cache.exists():
                tar.add(self.mutation_cache, arcname=MUTATION_CACHE)
            if self.store_arc and self.witness_store and self.witness_store.is_dir():
                for w in sorted(self.witness_store.glob("*.json")):
                    tar.add(w, arcname=f"{self.store_arc}/{w.name}")
            for pdf in sorted(self.docs.glob("*.pdf")) if self.docs.is_dir() else ():
                tar.add(pdf, arcname=f"{DOCS}/{pdf.name}")
        return buf.getvalue()

    async def _session(self, argv: list[str]) -> subprocess.CompletedProcess:
        t, rec = time.monotonic(), {"tool": argv[0]}

        def lap(name: str) -> None:
            nonlocal t
            rec[f"{name}_s"] = round(time.monotonic() - t, 1)
            t = time.monotonic()

        data = self._upload(argv)
        rec["upload_bytes"] = len(data)
        r = self.root
        async with self.provision() as rt:
            lap("create")
            rec["image_cached"] = getattr(getattr(rt, "info", None), "image_cached", None)
            await rt.write(f"{r}/.cb-up.tgz", data)
            up = await rt.run(["sh", "-c", f"cd {shlex.quote(r)} && tar xzf .cb-up.tgz && rm .cb-up.tgz"], {})
            if up.exit_code != 0:
                raise RuntimeError(f"unpacking the upload failed: {up.stderr[-1000:]}")
            lap("upload")
            async with asyncio.timeout(self.timeout):
                p = await rt.run(argv, {"HOME": f"{r}/.home", "PYTHONDONTWRITEBYTECODE": "1"})
            lap("run")
            # Whatever exists of the outputs, also after a failure: witness and mutation
            # entries are decisions computed before it, which the local executor keeps too.
            outs = [x for x in (_flag(argv, "--out"), _flag(argv, "--witness-cache"), MUTATION_CACHE,
                                self.store_arc) if x]
            pack = await rt.run(["sh", "-c", 'cd "$1" && shift && uname -m && ls -d -- "$@" 2>/dev/null '
                                 '| tar czf .cb-down.tgz --exclude=.formal.lock -T -', "sh", r, *outs], {})
            if pack.exit_code != 0:
                raise RuntimeError(f"packing the outputs failed: {pack.stderr[-1000:]}")
            rec["machine"] = pack.stdout.strip()
            self._apply(argv, await rt.read(f"{r}/.cb-down.tgz"))
            lap("download")
        lap("teardown")
        rec["exit"] = p.exit_code
        with self._merge:
            self.calls.append(rec)
        print("prime: " + " ".join(f"{k}={v}" for k, v in rec.items()), file=sys.stderr, flush=True)
        return subprocess.CompletedProcess(argv, p.exit_code, p.stdout, p.stderr)

    def _apply(self, argv: list[str], data: bytes) -> None:
        """Write the downloaded outputs into the local run: the result, new witness
        entries (never overwriting one); and into the shared caches: new mutation-cache
        and witness-store entries (merged)."""
        out, wc = _flag(argv, "--out"), _flag(argv, "--witness-cache")
        with tempfile.TemporaryDirectory() as d, tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(d, filter="data")
            got = Path(d)
            if out and (got / out).is_file():
                (ROOT / out).parent.mkdir(parents=True, exist_ok=True)
                (ROOT / out).write_bytes((got / out).read_bytes())
            if wc and (got / wc).is_dir():
                for w in sorted((got / wc).glob("*.json")):
                    dest = ROOT / wc / w.name
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        tmp = dest.with_name(f".{w.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                        tmp.write_bytes(w.read_bytes())
                        os.replace(tmp, dest)
            if (got / MUTATION_CACHE).is_file():
                gates.merge_cache(self.mutation_cache, json.loads((got / MUTATION_CACHE).read_text()))
            if self.store_arc and self.witness_store and (got / self.store_arc).is_dir():
                for w in sorted((got / self.store_arc).glob("*.json")):
                    gates.store_witness(self.witness_store, w.stem, json.loads(w.read_text()))
