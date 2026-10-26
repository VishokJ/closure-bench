"""Load is not a decision: a timeout is retried once, then aborts as infrastructure.

Pure: grader.simulate is replaced by a fake that returns scripted statuses.
"""

import types

import pytest

from closure_core import infra, mutants
from closure_core.design import load_design
from closure_core.design import find_repo_root

PACK = find_repo_root() / "designs" / "uart"


def fake(monkeypatch, statuses, module=infra):
    calls = []

    def simulate(design, tb_text, **kw):
        calls.append(kw)
        st = statuses.pop(0)
        return types.SimpleNamespace(sim=types.SimpleNamespace(status=st), points=[])

    monkeypatch.setattr(module.grader, "simulate", simulate)
    return calls


def test_one_timeout_is_retried(monkeypatch):
    for first in infra.LOAD_STATUSES:
        calls = fake(monkeypatch, [first, "ok"])
        assert infra.simulate(None, "tb").sim.status == "ok" and len(calls) == 2


def test_two_timeouts_abort_as_infrastructure(monkeypatch):
    fake(monkeypatch, ["timeout", "compile_timeout"])
    with pytest.raises(infra.InfraError, match="compile_timeout twice"):
        infra.simulate(None, "tb")


def test_other_statuses_are_decisions(monkeypatch):
    for st in ("ok", "runtime_error", "no_finish", "compile_error"):
        calls = fake(monkeypatch, [st])
        assert infra.simulate(None, "tb").sim.status == st and len(calls) == 1


def test_default_jobs_leaves_two_cores(monkeypatch):
    monkeypatch.setattr(infra.os, "cpu_count", lambda: 11)
    assert infra.default_jobs() == 9
    monkeypatch.setattr(infra.os, "cpu_count", lambda: 2)
    assert infra.default_jobs() == 1


# --- mutation runs ----------------------------------------------------------------------

@pytest.fixture
def design():
    return load_design(PACK)


def mutant(design):
    f, (lo, hi) = next(iter(design.mutate.items()))
    return mutants.generate(f, lo, hi)[0]


def test_mutant_hang_is_a_kill_after_one_retry(monkeypatch, design):
    fake(monkeypatch, ["timeout", "timeout"], mutants)
    cache = {}
    assert mutants.simulate(design, "tb", "tb", mutant(design), cache=cache)["status"] == "timeout"
    assert len(cache) == 1  # a real hang: cached


def test_mutant_timeout_once_is_load(monkeypatch, design):
    fake(monkeypatch, ["timeout", "ok"], mutants)
    cache = {}
    assert mutants.simulate(design, "tb", "tb", mutant(design), cache=cache)["status"] == "ok"
    assert list(cache.values())[0]["status"] == "ok"


@pytest.mark.parametrize("statuses, with_mutant", [
    (["timeout", "timeout"], False),                  # the unmutated RTL never hangs: load
    (["compile_timeout", "compile_timeout"], True),   # compiling is never a kill
])
def test_load_in_mutation_runs_is_not_cached(monkeypatch, design, statuses, with_mutant):
    fake(monkeypatch, statuses, mutants)
    cache = {}
    with pytest.raises(infra.InfraError):
        mutants.simulate(design, "tb", "tb", mutant(design) if with_mutant else None, cache=cache)
    assert cache == {}
