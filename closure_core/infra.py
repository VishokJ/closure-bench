"""Infrastructure failures are not decisions.

A simulation that hits its compile or run timeout says more about the machine
(load, parallel containers) than about the testbench, so no gate may reject a
candidate because of one: the simulation is retried once, one retry at a time
in this process, and a second timeout raises InfraError. The candidate is then
aborted as infrastructure: no gate result is written, nothing is cached or
counted, and a resume or replay runs it again. A replay can therefore only
fail to reproduce a decision because of load, never flip it.

Cost: a testbench that really hangs (a gold that never reaches $finish) is
aborted too, so the proposer gets no repair turn for it.
"""

from __future__ import annotations

import os
import threading

from closure_core import grader

LOAD_STATUSES = ("compile_timeout", "timeout")
_ONE_AT_A_TIME = threading.Lock()


class InfraError(RuntimeError):
    """The machine failed, not the candidate: abort, record nothing, retry later."""


def default_jobs() -> int:
    """Default parallel simulations: every core but two, so timeouts stay rare."""
    return max(1, (os.cpu_count() or 3) - 2)


def retry_once(run):
    """run() -> (result, status). On a load status, run once more holding the
    process-wide retry lock, and return that run. The caller decides what a
    second timeout means."""
    res, status = run()
    if status not in LOAD_STATUSES:
        return res, status
    with _ONE_AT_A_TIME:
        return run()


def simulate(design, tb_text: str, **kw) -> grader.Simulation:
    """grader.simulate for the gates: a timeout twice is an InfraError, never a status."""
    def run():
        r = grader.simulate(design, tb_text, **kw)
        return r, r.sim.status

    s, status = retry_once(run)
    if status in LOAD_STATUSES:
        raise InfraError(f"simulation hit {status} twice (the second time with no other retry running); "
                         f"treating it as load, not as a decision")
    return s
