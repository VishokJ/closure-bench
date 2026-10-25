"""Build and run one Verilator simulation with coverage.

Every run gets explicit time limits and a structured status, because
submitted testbenches will fail to compile, crash, hang, or stop early.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

SIM_MAIN = Path(__file__).with_name("sim_main.cpp")

# Fixed flags: the same build for every testbench, so coverage is comparable.
VERILATOR_FLAGS = (
    "--cc", "--exe", "--build", "--timing",
    "--prefix", "Vtop",
    "--coverage-line", "--coverage-toggle", "--coverage-user",
    "--x-assign", "0", "--x-initial", "0",  # deterministic: no random X values
    "-Wno-fatal",
)

LOG_TAIL = 4000  # characters of log kept in results


@dataclass(frozen=True)
class SimResult:
    status: str            # ok | compile_error | compile_timeout | timeout | runtime_error | no_finish
    coverage_file: Path | None
    compile_log: str       # tail
    run_log: str           # tail
    compile_s: float
    run_s: float
    exit_code: int | None


def _tail(path: Path, n: int = LOG_TAIL) -> str:
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - n))
        return f.read().decode(errors="replace")


def _run(argv: list[str], cwd: Path, log: Path, timeout: float, env: dict | None = None):
    """Run a command in its own process group; kill the whole group on timeout.

    Output goes to a file, not a pipe, so a testbench printing in a loop until
    the timeout cannot exhaust the grader's memory; only the tail is kept.
    """
    start = time.monotonic()
    with log.open("wb") as out:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # exited between the timeout and the kill
            proc.wait()
            timed_out = True
    return (None if timed_out else proc.returncode), _tail(log), time.monotonic() - start, timed_out


def build_and_run(
    workdir: Path,
    sources: list[Path],
    top: str,
    *,
    compile_timeout: float = 120.0,
    run_timeout: float = 60.0,
) -> SimResult:
    workdir = workdir.resolve()
    build = workdir / "build"
    cov = workdir / "coverage.dat"

    argv = ["verilator", *VERILATOR_FLAGS, "--top-module", top,
            "--Mdir", str(build), "-o", "sim", str(SIM_MAIN), *map(str, sources)]
    code, clog, compile_s, timed_out = _run(argv, workdir, workdir / "compile.log", compile_timeout)
    if timed_out:
        return SimResult("compile_timeout", None, clog, "", compile_s, 0.0, None)
    if code != 0:
        return SimResult("compile_error", None, clog, "", compile_s, 0.0, code)

    env = {**os.environ, "COVERAGE_FILE": str(cov)}
    code, rlog, run_s, timed_out = _run([str(build / "sim")], workdir, workdir / "run.log",
                                        run_timeout, env)
    if timed_out:
        status = "timeout"
    elif code == 2:
        status = "no_finish"       # sim_main: events ran out before $finish
    elif code != 0:
        status = "runtime_error"   # $fatal, $stop, assertion or crash
    elif not cov.is_file():
        status = "runtime_error"
    else:
        status = "ok"
    return SimResult(status, cov if status == "ok" else None, clog, rlog, compile_s, run_s, code)


def verilator_version() -> str:
    out = subprocess.run(["verilator", "--version"], capture_output=True, text=True)
    return out.stdout.strip()
