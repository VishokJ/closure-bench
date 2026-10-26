"""ClosureConfig.items: keep only the named plan items (single mode)."""

import pytest

pytest.importorskip("verifiers")
from closure_bench.taskset import ClosureBenchTaskset, ClosureConfig  # noqa: E402


def _ids(**cfg):
    return [t.data.id for t in ClosureBenchTaskset(ClosureConfig(**cfg)).load()]


def test_default_loads_every_item_with_a_gold():
    assert len(_ids()) == len(_ids(items=None)) > 2


def test_items_keeps_only_those_in_plan_order():
    assert _ids(items=["T1", "R2"]) == ["uart/R2", "uart/T1"]


def test_unknown_item_raises():
    with pytest.raises(ValueError, match="NOPE"):
        _ids(items=["R1", "NOPE"])


def test_items_only_in_single_mode():
    with pytest.raises(ValueError, match="single"):
        _ids(tasks="multi", items=["R1"])
    with pytest.raises(ValueError, match="single"):
        _ids(tasks="campaign", items=["R1"])
