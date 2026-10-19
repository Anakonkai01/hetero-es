"""Cancellation preserves the last complete model and never applies a partial generation."""
import threading

import pytest

from test_coordinator import Env, reward_of
from heteroes.coordinator import RunCancelled
from heteroes.eval.candidate import model_weights_sha256
from heteroes.worker_runtime import WorkerRuntime


def test_cancel_before_run_never_opens_a_generation(tmp_path):
    flag = threading.Event()
    flag.set()
    env = Env(tmp_path, cancel_requested=flag.is_set)
    try:
        with pytest.raises(RunCancelled):
            env.coordinator.run(3)
        assert env.ledger.list_generations("exp") == []
        assert env.coordinator.server.job["state"] == "CANCELLED"
    finally:
        env.close()


def test_cancel_after_results_before_record_does_not_update(tmp_path, monkeypatch):
    flag = threading.Event()
    env = Env(tmp_path, cancel_requested=flag.is_set)
    initial = model_weights_sha256(env.model, env.schema)
    original_wait = env.coordinator._wait_until_complete
    def wait(number):
        original_wait(number)
        flag.set()
    monkeypatch.setattr(env.coordinator, "_wait_until_complete", wait)
    env.start_workers()
    try:
        with pytest.raises(RunCancelled):
            env.coordinator.run(3)
        assert env.ledger.get_update("exp", 0) is None
        assert model_weights_sha256(env.model, env.schema) == initial
    finally:
        env.close()


def test_cancel_during_apply_finishes_write_ahead_transaction(tmp_path, monkeypatch):
    flag = threading.Event()
    env = Env(tmp_path, cancel_requested=flag.is_set)
    apply = env.coordinator._apply_record
    def applying(record):
        flag.set()
        return apply(record)
    monkeypatch.setattr(env.coordinator, "_apply_record", applying)
    env.start_workers()
    try:
        with pytest.raises(RunCancelled):
            env.coordinator.run(3)
        stored = env.ledger.get_update("exp", 0)
        assert stored.child_weights_sha256 == model_weights_sha256(env.model, env.schema)
        assert (tmp_path / "published" / (stored.child_weights_sha256 + ".bin")).is_file()
        assert len(env.ledger.list_generations("exp")) == 1
    finally:
        env.close()


def test_cancel_during_record_construction_still_discards_generation(tmp_path, monkeypatch):
    from heteroes.generation_record import GenerationRecord
    flag = threading.Event()
    env = Env(tmp_path, cancel_requested=flag.is_set)
    original = GenerationRecord.from_results
    def build(*args, **kwargs):
        record = original(*args, **kwargs)
        flag.set()
        return record
    monkeypatch.setattr(GenerationRecord, "from_results", build)
    env.start_workers()
    try:
        with pytest.raises(RunCancelled):
            env.coordinator.run(3)
        assert env.ledger.get_update("exp", 0) is None
    finally:
        env.close()


def test_cancel_blocks_new_leases_but_accepts_inflight_result(tmp_path):
    flag = threading.Event()
    env = Env(tmp_path, cancel_requested=flag.is_set)
    # Open the generation without running an update.
    from heteroes.manifest import CandidateDescriptor, derive_seed
    from heteroes.worker_api import WorkerAPI
    descriptors = [CandidateDescriptor(recipe_hash=env.recipe.hash,
        parent_weights_sha256=env.coordinator.parent_sha256, experiment_id="exp",
        generation=0, index=i, seed=derive_seed("exp", 0, i)) for i in range(4)]
    env.ledger.open_generation(descriptors)
    api = WorkerAPI(env.ledger, "exp", 0, 60, cancel_requested=flag.is_set)
    try:
        work = api.handle("lease", {"worker_id": "w1"})["work"]
        assert work is not None
        flag.set()
        assert api.handle("lease", {"worker_id": "w2"})["work"] is None
        reply = api.handle("submit_result", {"descriptor": work["descriptor"],
            "attempt_number": work["attempt_number"], "token": work["token"],
            "reward": reward_of(descriptors[0])})
        assert reply["ok"] is True
        assert env.ledger.get_generation_status("exp", 0).committed == 1
    finally:
        env.close()


def test_worker_recognizes_cancelled_without_touching_model():
    class Client:
        def get_json(self, path):
            return {"ok": True, "job": {"state": "CANCELLED"}}
    events = []
    runtime = WorkerRuntime("w", Client(), object(), "/unused", log=events.append)
    assert runtime.run(threading.Event()) == "cancelled"
    assert events[-1]["reason"] == "cancelled"
