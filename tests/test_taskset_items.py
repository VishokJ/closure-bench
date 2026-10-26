"""ClosureConfig.items: keep only the named plan items (single, campaign) or multi tasks."""

import pytest

pytest.importorskip("verifiers")
from closure_bench.taskset import ClosureBenchTaskset, ClosureConfig  # noqa: E402


def _tasks(**cfg):
    return ClosureBenchTaskset(ClosureConfig(**cfg)).load()


def _ids(**cfg):
    return [t.data.id for t in _tasks(**cfg)]


def test_default_loads_every_item_with_a_gold():
    assert len(_ids()) == len(_ids(items=None)) > 2


def test_items_keeps_only_those_in_plan_order():
    assert _ids(items=["T1", "R2"]) == ["uart/R2", "uart/T1"]


def test_unknown_item_raises():
    with pytest.raises(ValueError, match="NOPE"):
        _ids(items=["R1", "NOPE"])


def test_campaign_targets_come_from_items():
    tasks = _tasks(tasks="campaign", items=["T2", "R1", "R3"])
    assert [(t.data.id, t.data.targets, t.data.max_files) for t in tasks] == [
        ("uart/campaign_uart_rx", ["R1", "R3"], 2), ("uart/campaign_uart_tx", ["T2"], 1)]
    # One module only: the other has no campaign.
    assert _ids(tasks="campaign", items=["R1"]) == ["uart/campaign_uart_rx"]
    with pytest.raises(ValueError, match="NOPE"):
        _ids(tasks="campaign", items=["R1", "NOPE"])


def test_multi_items_name_multi_tasks():
    assert _ids(tasks="multi", items=["M2"]) == ["uart/M2"]
    with pytest.raises(ValueError, match="R1"):
        _ids(tasks="multi", items=["R1"])
