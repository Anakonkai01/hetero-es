"""
D10: after a restore mismatch a worker recovers once per run: it reloads its base weights, takes the canonical parent,
passes a perturb/restore self-test and rejoins at the next generation under the alias `<worker>~r1`. The ledger
quarantine of the original identity stays. A second fault, a failed self-test or no reload function leaves it quarantined.
"""

import json

import pytest

from heteroes.ledger import FailureKind
from heteroes.restore_recovery import CoordinatorRecoveries, alias, base_of
from heteroes.worker import CandidateFailed
from heteroes.worker_api import WorkerAPI
from test_worker_runtime import Coordinator, WorkerSide, wait_for


class RecoveringCoordinator(Coordinator):
    def __init__(self, tmp_path, **options):
        super().__init__(tmp_path, **options)
        self.recoveries = CoordinatorRecoveries(tmp_path / "restore-recoveries.json")

    def open_generation(self, generation, parent):
        super().open_generation(generation, parent)
        api = WorkerAPI(self.ledger, "exp", generation, lease_seconds=self.lease_seconds, recoveries=self.recoveries)
        self.server.set_generation(api, self.job(generation, parent))


@pytest.fixture
def coordinator(tmp_path):
    coordinator = RecoveringCoordinator(tmp_path)
    coordinator.open_generation(0, coordinator.parent)
    yield coordinator
    coordinator.close()


def faults(times):
    calls = {"n": 0}

    def evaluate():
        calls["n"] += 1
        if calls["n"] <= times:
            raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    return evaluate


def committed_by(coordinator, generation):
    return {worker for g, _, worker in coordinator.ledger.list_committed_attempts("exp") if g == generation}


def test_alias_names():
    assert alias("w") == "w~r1" and base_of("w~r1") == "w" and base_of("w") is None
    with pytest.raises(ValueError):
        alias("w~r1")


def test_a_worker_recovers_once_and_rejoins_at_the_next_generation(coordinator, monkeypatch):
    reloads = []
    side = WorkerSide(coordinator, monkeypatch, evaluate=faults(1), reload_base=reloads.append).start()
    assert wait_for(lambda: "restore_recovery_rejoined" in side.kinds())
    helper = WorkerSide(coordinator, monkeypatch, name="worker-b").start()  # finishes generation 0
    assert coordinator.wait_complete(0)
    helper.stop.set()
    assert helper.join() == "stopped"
    assert "worker-a~r1" not in committed_by(coordinator, 0)  # probation: no work before the boundary
    coordinator.open_generation(1, coordinator.parent)
    assert coordinator.wait_complete(1)
    assert committed_by(coordinator, 1) == {"worker-a~r1"}
    coordinator.finish()
    assert side.join() == "finished"
    assert len(reloads) == 1 and reloads[0] is side.model
    assert [q.worker_id for q in coordinator.ledger.list_quarantined()] == ["worker-a"]  # the record stays
    budget = json.loads(next(side.dir.parent.glob(".delivery-*/*.recovery.json")).read_text())
    assert [entry["completed"] for entry in budget.values()] == [True]
    assert json.loads((coordinator.models_dir.parent / "restore-recoveries.json").read_text())["worker-a"] == {
        "alias": "worker-a~r1",
        "faultGeneration": 0,
    }


def test_a_second_restore_fault_needs_an_operator(coordinator, monkeypatch):
    # every WorkerSide replaces the same evaluate hook, so one switch decides when evaluations fail
    switch = {"fail": 1}

    def evaluate():
        if switch["fail"]:
            switch["fail"] -= 1
            raise CandidateFailed(FailureKind.RESTORE_MISMATCH)

    reloads = []
    side = WorkerSide(coordinator, monkeypatch, evaluate=evaluate, reload_base=reloads.append).start()
    assert wait_for(lambda: "restore_recovery_rejoined" in side.kinds())
    helper = WorkerSide(coordinator, monkeypatch, name="worker-b", evaluate=evaluate).start()
    assert coordinator.wait_complete(0)
    helper.stop.set()
    helper.join()
    switch["fail"] = 1  # the recovered worker's next candidate fails to restore again
    coordinator.open_generation(1, coordinator.parent)
    assert side.join() == "quarantined"
    assert len(reloads) == 1
    assert {q.worker_id for q in coordinator.ledger.list_quarantined()} == {"worker-a", "worker-a~r1"}


def test_without_a_reload_function_a_restore_fault_still_stops_the_worker(coordinator, monkeypatch):
    side = WorkerSide(coordinator, monkeypatch, evaluate=faults(1)).start()
    assert side.join() == "quarantined"
    assert "restore_recovery_started" not in side.kinds()


def test_a_failed_self_test_keeps_the_quarantine_and_the_budget_spent(coordinator, monkeypatch):
    def broken_selftest():
        raise RuntimeError("the self-test perturbation did not restore to the parent")

    side = WorkerSide(coordinator, monkeypatch, evaluate=faults(1), reload_base=lambda model: None)
    monkeypatch.setattr(side.executor, "selftest_restore", broken_selftest)
    side.start()
    assert side.join() == "quarantined"
    assert "restore_recovery_failed" in side.kinds() and "restore_recovery_rejoined" not in side.kinds()
    again = WorkerSide(coordinator, monkeypatch, evaluate=faults(0), reload_base=lambda model: None)
    again.dir = side.dir
    assert again.start().join() == "quarantined"  # a restart does not give a second recovery


def test_a_restart_during_the_recovery_finishes_it_under_the_alias(coordinator, monkeypatch):
    first = WorkerSide(coordinator, monkeypatch, evaluate=faults(1)).start()
    assert first.join() == "quarantined"  # this process had no reload function
    reloads = []
    second = WorkerSide(coordinator, monkeypatch, reload_base=reloads.append)
    second.runtime()._budget.spend("worker-a")  # the earlier process spent it and died before rejoining
    second.start()
    assert wait_for(lambda: "restore_recovery_rejoined" in second.kinds())
    assert len(reloads) == 1
    rejoined = next(e for e in second.events if e["event"] == "restore_recovery_rejoined")
    assert rejoined["alias"] == rejoined["worker_id"] == "worker-a~r1"
    coordinator.finish()


def test_only_the_alias_of_a_worker_quarantined_for_a_restore_fault_is_admitted(coordinator):
    api = coordinator.server.api
    reply = api.handle("lease", {"worker_id": "worker-z~r1"})
    assert reply["ok"] is False and reply["error"]["code"] == "worker_quarantined"
    assert api._owns("worker-z", "worker-z~r1") and not api._owns("worker-y", "worker-z~r1")
    plain = WorkerAPI(coordinator.ledger, "exp", 0, lease_seconds=60)  # no recoveries configured
    assert not plain._owns("worker-z", "worker-z~r1")
