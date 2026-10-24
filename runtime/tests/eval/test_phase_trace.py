"""Phase telemetry must distinguish work and never alter a candidate's failure or result."""

import json

import pytest
import torch
from torch import nn

from heteroes.eval.phase_trace import PhaseTrace, storage_inventory


def test_trace_separates_refresh_from_rollout_with_safe_execution_identity():
    events = []
    ticks = iter((10.0, 10.25, 12.0, 14.5))
    trace = PhaseTrace(events.append, clock=lambda: next(ticks))

    for phase in ("refresh", "rollout"):
        with trace.phase(phase, candidate_id="exp/g2/c3", generation=2, recipe_hash="a" * 64, device="cpu"):
            pass

    assert [event["phase"] for event in events] == ["refresh", "rollout"]
    assert [event["wallSeconds"] for event in events] == [0.25, 2.5]
    assert all(event["status"] == "ok" and event["timingKind"] == "host_wall" for event in events)
    assert all(event["candidateId"] == "exp/g2/c3" and event["generation"] == 2 for event in events)
    assert all(event["recipeHash"] == "a" * 64 and event["device"] == "cpu" for event in events)
    assert all(event["formatVersion"] == 1 and event["event"] == "phase_timing" for event in events)
    assert json.loads(json.dumps(events, allow_nan=False)) == events


def test_a_failing_phase_is_measured_without_exposing_the_exception_message():
    events = []
    ticks = iter((1.0, 3.0))
    trace = PhaseTrace(events.append, clock=lambda: next(ticks))
    error = RuntimeError("private payload must not become telemetry")

    with pytest.raises(RuntimeError) as caught:
        with trace.phase("rollout", candidate_id="exp/g0/c0", generation=0, recipe_hash="a" * 64, device="cpu"):
            raise error

    assert caught.value is error
    assert events[0]["status"] == "error" and events[0]["wallSeconds"] == 2.0
    assert "private payload" not in json.dumps(events)


@pytest.mark.parametrize("operation_error", (False, True))
def test_a_broken_telemetry_sink_cannot_replace_the_result_or_original_error(operation_error):
    def broken_sink(event):
        raise OSError("telemetry storage is full")

    trace = PhaseTrace(broken_sink)
    error = ValueError("the actual operation failed")

    def operation():
        with trace.phase("restore", candidate_id="exp/g0/c0", generation=0, recipe_hash="a" * 64, device="cpu"):
            if operation_error:
                raise error
            return "result"

    if operation_error:
        with pytest.raises(ValueError) as caught:
            operation()
        assert caught.value is error
    else:
        assert operation() == "result"
    assert trace.dropped_events == 1


@pytest.mark.parametrize("end", (float("nan"), float("inf"), -1.0))
def test_invalid_elapsed_time_is_dropped_instead_of_publishing_a_false_duration(end):
    events = []
    ticks = iter((0.0, end))
    trace = PhaseTrace(events.append, clock=lambda: next(ticks))
    with trace.phase("perturb", candidate_id="exp/g0/c0", generation=0, recipe_hash="a" * 64, device="cpu"):
        pass
    assert events == [] and trace.dropped_events == 1


class TiedStorage(nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = nn.Embedding(10, 4, dtype=torch.float16)
        self.head = nn.Linear(4, 10, bias=False, dtype=torch.float16)
        self.head.weight = self.embed.weight
        self.register_buffer("view", self.embed.weight.detach().view(-1)[:3])
        self.register_buffer("separate", torch.zeros(5, dtype=torch.float32))


def test_inventory_counts_physical_storage_once_for_ties_views_and_repeated_roles():
    model = TiedStorage()
    before = model.embed.weight.detach().clone()

    actual = storage_inventory({"worker": model, "validation": model})

    assert actual["roles"] == {
        "worker": {"cpu": {"storageBytes": 100, "storages": 2}},
        "validation": {"cpu": {"storageBytes": 100, "storages": 2}},
    }
    assert actual["unique"] == {"cpu": {"storageBytes": 100, "storages": 2}}
    assert torch.equal(model.embed.weight, before)
    assert json.loads(json.dumps(actual)) == actual


def test_inventory_detects_a_shadow_and_ignores_empty_storages():
    import copy

    model = nn.Linear(4, 3, bias=False, dtype=torch.float16)
    shadow = copy.deepcopy(model).float()
    model.register_buffer("empty", torch.empty(0))

    actual = storage_inventory({"live": model, "shadow": shadow})

    assert actual["roles"]["live"] == {"cpu": {"storageBytes": 24, "storages": 1}}
    assert actual["roles"]["shadow"] == {"cpu": {"storageBytes": 48, "storages": 1}}
    assert actual["unique"] == {"cpu": {"storageBytes": 72, "storages": 2}}


def test_a_meta_model_is_unknown_storage_not_a_zero_byte_measurement():
    with pytest.raises(ValueError, match="meta"):
        storage_inventory({"unallocated": nn.Linear(4, 3, device="meta")})
