"""A late coordinator snapshot must not undo a storage-verified final recovery checkpoint."""

import json
import pytest

from backend.services.scheduling import cloud_sync_projection
from backend.tests import test_recovery_storage as recovery_fixtures

storage = recovery_fixtures.storage
manifest = recovery_fixtures.manifest
upload = recovery_fixtures.upload


def body():
    return {
        "experimentId": "b" * 32,
        "status": "COMPLETED",
        "completedGenerations": 2,
        "cloudSync": {"status": "READY", "lastCloudGeneration": 1, "pointId": "a" * 32},
    }


@pytest.mark.parametrize(
    "incoming", [{"status": "PENDING"}, {"status": "READY", "lastCloudGeneration": 0, "pointId": "c" * 32}]
)
def test_verified_final_survives_late_pending_or_older_ready_snapshot(storage, incoming):
    recovery, objects, store = storage
    final = {**manifest(), "generation": 1, "final": True}
    upload(recovery, objects, final)
    with store.db() as db:
        result = cloud_sync_projection(db, body(), incoming)
    assert result == {"status": "READY", "lastCloudGeneration": 1, "pointId": "a" * 32}
    assert json.loads(objects.data["manifests/" + "a" * 32 + ".json"])["final"] is True


@pytest.mark.parametrize("change", ["pending", "nonfinal", "older", "other-run", "running"])
def test_unverified_nonfinal_older_or_foreign_point_never_claims_final_sync(storage, change):
    recovery, objects, store = storage
    final = {**manifest(), "generation": 1, "final": True}
    current = body()
    if change == "nonfinal":
        final["final"] = False
    if change == "older":
        final["generation"] = 0
    if change == "other-run":
        final["runId"] = "d" * 32
    if change == "running":
        current["status"] = "RUNNING"
    if change == "pending":
        recovery.begin(final)
    else:
        upload(recovery, objects, final)
    with store.db() as db:
        result = cloud_sync_projection(db, current, {"status": "PENDING", "errorType": "TimeoutError"})
    assert result["status"] == "PENDING"
    assert result["errorType"] == "TimeoutError"


def test_ready_storage_wins_even_when_the_previous_projection_never_saw_it(storage):
    recovery, objects, store = storage
    upload(recovery, objects, {**manifest(), "generation": 1, "final": True})
    current = body()
    current["cloudSync"] = {"status": "PENDING"}
    with store.db() as db:
        assert cloud_sync_projection(db, current, {"status": "PENDING"}) == {
            "status": "READY",
            "lastCloudGeneration": 1,
            "pointId": "a" * 32,
        }


@pytest.mark.parametrize("order", ["storage-first", "snapshot-first"])
def test_real_scheduler_and_storage_reconcile_both_completion_orders(storage, monkeypatch, order):
    recovery, objects, store = storage
    active = store.create(
        "admin",
        {
            "workerIds": ["worker"],
            "coordinatorDeviceId": "coordinator",
            "task": "arith16",
            "candidatesPerGeneration": 2,
            "maxGenerations": 2,
            "alpha": 0.001,
            "sigma": 0.001,
            "decodeEngine": "hf_generate",
            "schedulerPolicy": "greedy",
            "syncMode": "synchronous",
        },
    )
    final = {**manifest(), "runId": active["experimentId"], "generation": 1, "final": True}
    if order == "storage-first":
        upload(recovery, objects, final)
    monkeypatch.setattr(store.runtime, "submit", lambda config: None)
    monkeypatch.setattr(
        store.runtime,
        "snapshot",
        lambda run_id: {
            "state": {"status": "COMPLETED"},
            "generations": [],
            "completedGenerationCount": 2,
            "cloudSync": {"status": "PENDING"},
        },
    )
    store.scheduling._dispatch_run(active)
    if order == "snapshot-first":
        assert store.get(active["experimentId"])["cloudSync"]["status"] == "PENDING"
        upload(recovery, objects, final)
    saved = store.get(active["experimentId"])
    assert saved["status"] == "COMPLETED" and saved["completedGenerations"] == 2
    assert saved["cloudSync"] == {"status": "READY", "lastCloudGeneration": 1, "pointId": final["pointId"]}
