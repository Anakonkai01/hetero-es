"""
D11: a heartbeat proves contact, not progress. A worker that reports stage progress keeps a generation alive only while
its units grow; the generation's hard cap is finite, explicit and counts from the generation's first start, so a
coordinator restart never extends it. Workers older than progress reporting keep the ADR-009 heartbeat meaning.
"""

import json
import threading
import time

import pytest

from heteroes import progress
from heteroes.coordinator import CoordinatorError
from heteroes.http_transport import HttpClient
from heteroes.worker import StepKind, Worker
from test_coordinator import reward_of
from test_coordinator_recovery import World, final_hash


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.close()


def one_worker(coordinator, evaluate, *, reporting=True):
    stop = threading.Event()
    worker = Worker("w1", HttpClient(coordinator.url, timeout=10.0), evaluate, heartbeat_seconds=0.05)
    worker.client.progress_reporting = reporting

    def loop():
        while not stop.is_set():
            if worker.step().kind is StepKind.NO_WORK:
                time.sleep(0.005)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return lambda: (stop.set(), thread.join(timeout=10))


def advancing(descriptor):
    for _ in range(9):  # a long candidate made of short steps, each reported
        time.sleep(0.1)
        progress.advance("rollout")
    return reward_of(descriptor)


def stuck(descriptor):
    time.sleep(1.2)  # the compute hangs: heartbeats go on, the units do not move
    return reward_of(descriptor)


def test_heartbeats_with_growing_units_are_progress(world):
    coordinator = world.coordinator(stall_seconds=0.4, timeout_seconds=60)
    halt = one_worker(coordinator, advancing)
    summary = coordinator.run_generation(0)
    halt()
    assert summary["wait_seconds"] > 0.4 * 4
    assert final_hash(coordinator) == world.oracle(1)


def test_heartbeats_without_progress_are_a_stall(world):
    coordinator = world.coordinator(stall_seconds=0.4, timeout_seconds=60)
    before = final_hash(coordinator)
    halt = one_worker(coordinator, stuck)
    with pytest.raises(CoordinatorError, match="no progress"):
        coordinator.run_generation(0)
    halt()
    assert final_hash(coordinator) == before


def test_a_worker_without_progress_reporting_keeps_the_heartbeat_meaning(world):
    coordinator = world.coordinator(stall_seconds=0.4, timeout_seconds=60)
    halt = one_worker(coordinator, stuck, reporting=False)
    summary = coordinator.run_generation(0)
    halt()
    assert summary["wait_seconds"] > 0.4


def test_the_job_asks_for_progress_reports(world):
    coordinator = world.coordinator()
    assert coordinator._job(0, object())["progressReporting"] is True


def test_malformed_progress_is_refused():
    from heteroes.manifest import CandidateDescriptor
    from heteroes.worker_api import _decode_heartbeat

    descriptor = CandidateDescriptor("a" * 64, "b" * 64, "e", 0, 0, 1).to_dict()
    base = {"descriptor": descriptor, "attempt_number": 1, "token": "t"}
    assert _decode_heartbeat({**base, "progress": {"stage": "rollout", "units": 3}})[3] == ("rollout", 3)
    for bad in ({"stage": "nap", "units": 1}, {"stage": "rollout", "units": -1}, {"stage": "rollout"}, 7):
        with pytest.raises((ValueError, TypeError)):
            _decode_heartbeat({**base, "progress": bad})


def test_the_hard_cap_counts_from_the_first_start_across_restarts(world, tmp_path):
    clock = tmp_path / "generation-clock.json"
    clock.write_text(json.dumps({"exp/g0": time.time() - 50}))  # a previous coordinator started g0 50 s ago
    coordinator = world.coordinator(stall_seconds=None, timeout_seconds=51, generation_clock_path=clock)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="first start"):
        coordinator.run_generation(0)  # nobody works: the cap ends after about 1 s, not 51 s
    assert time.monotonic() - started < 10
    assert json.loads(clock.read_text()) == {"exp/g0": pytest.approx(time.time() - 50, abs=15)}


def test_a_new_generation_records_its_first_start(world, tmp_path):
    clock = tmp_path / "generation-clock.json"
    coordinator = world.coordinator(stall_seconds=None, timeout_seconds=0.3, generation_clock_path=clock)
    with pytest.raises(TimeoutError):
        coordinator.run_generation(0)
    first = json.loads(clock.read_text())["exp/g0"]
    again = world.coordinator(stall_seconds=None, timeout_seconds=0.3, generation_clock_path=clock)
    with pytest.raises(TimeoutError):
        again.run_generation(0)
    assert json.loads(clock.read_text())["exp/g0"] == first


@pytest.mark.parametrize(
    "config, message",
    [
        ({"hardCapSeconds": 10}, "hardCapSeconds"),
        ({"hardCapSeconds": float("inf")}, "hardCapSeconds"),
        ({"stallSeconds": 5}, "stallSeconds"),
        ({"hardCapSeconds": 600, "stallSeconds": 600}, "shorter"),
        ({"hardCapSeconds": True}, "hardCapSeconds"),
    ],
)
def test_watchdog_settings_are_finite_and_consistent(config, message):
    from heteroes.v3.options import validate_watchdog

    with pytest.raises(ValueError, match=message):
        validate_watchdog(config)


def test_explicit_hard_cap_bounds_the_measured_limit():
    from heteroes.product.runner import generation_limit

    assert generation_limit(5000.0) == 5000.0
    assert generation_limit(5000.0, 3600) == 3600.0 and generation_limit(1800.0, 3600) == 1800.0


def test_progress_is_sent_only_when_the_job_asks_for_it():
    from heteroes.manifest import CandidateDescriptor
    from heteroes.worker import Assignment, WorkerClient

    sent = []

    def transport(operation, payload):
        sent.append(payload)
        return {"ok": True, "deadline": 1.0}

    client = WorkerClient("w", transport)
    work = Assignment(CandidateDescriptor("a" * 64, "b" * 64, "e", 0, 0, 1), 1, "t", 0.0)
    client.heartbeat(work)
    client.progress_reporting = True
    client.heartbeat(work)
    assert "progress" not in sent[0]  # an older coordinator refuses unknown fields: never send one it did not ask for
    assert set(sent[1]["progress"]) == {"stage", "units"}
