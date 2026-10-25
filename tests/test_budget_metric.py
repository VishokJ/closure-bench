"""The budget metric: turns and billed tokens per rollout (cost guard for the pilot)."""

import asyncio
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("verifiers")
from verifiers.v1.types import Usage  # noqa: E402

from closure_bench.taskset import ClosureTask  # noqa: E402


def _budget(trace):
    return asyncio.run(ClosureTask.budget(None, trace))


def test_sums_every_call_and_flags_the_cap():
    usage = Usage.aggregate([Usage(prompt_tokens=1000, completion_tokens=50, cached_input_tokens=800),
                             Usage(prompt_tokens=300, completion_tokens=20)])
    b = _budget(NS(num_turns=40, stop_condition="max_turns", usage=usage))
    assert b == {"turns": 40.0, "turn_cap_hit": 1.0, "prompt_tokens": 1300.0,
                 "cached_input_tokens": 800.0, "output_tokens": 70.0}


def _setup_with(agent_max_turns, data_max_turns):
    from closure_bench.taskset import ClosureBenchTaskset, ClosureConfig
    task = ClosureBenchTaskset(ClosureConfig(harness="bash", max_turns=data_max_turns)).load()[0]
    trace = NS(agent=NS(config=NS(harness=NS(id="bash"), max_turns=agent_max_turns)))
    return asyncio.run(task.setup(trace, runtime=None))


def test_setup_rejects_max_turns_mismatch():
    import verifiers.v1 as vf
    with pytest.raises(vf.TaskError, match="max_turns"):
        _setup_with(agent_max_turns=40, data_max_turns=None)
    with pytest.raises(vf.TaskError, match="max_turns"):
        _setup_with(agent_max_turns=None, data_max_turns=40)


def test_no_calls():
    b = _budget(NS(num_turns=0, stop_condition=None, usage=None))
    assert set(b.values()) == {0.0}
