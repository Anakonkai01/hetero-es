import copy
import json
import pytest
from backend.devices import AgentRuntime
from backend.store import Store
from labkit import boot, enable, pair, queued


def checkpoint():
    return {
        "pointId": "c" * 32,
        "generation": 0,
        "childWeightsSha256": "a" * 64,
        "parentWeightsSha256": "b" * 64,
        "verified": True,
    }


def paused_report(assignment, sequence=1):
    return {
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "sequence": sequence,
        "snapshot": {
            "state": {"status": "PAUSED", "pauseCheckpoint": checkpoint()},
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": [],
            "artifacts": [],
            "completedGenerationCount": 1,
        },
    }


def stopped(assignment, **changes):
    return {
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "coordinatorAlive": False,
        "workerAlive": False,
        **changes,
    }


def test_pause_keeps_reservation_until_checkpoint_and_every_process_stops(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    assert client.post(f"/api/v1/experiments/{rid}/pause", headers=admin).status_code == 200
    assert client.post(f"/api/v1/experiments/{rid}/resume", headers=admin).status_code == 409
    assert sum(c["kind"] == "PAUSE_ASSIGNMENT" for c in runtime.commands(device["deviceId"])) == 1
    boot(
        client,
        auth,
        "boot-1",
        contribution=True,
        reports=[paused_report(assignment)],
        processes=[stopped(assignment, workerAlive=True)],
    )
    store.dispatch_once()
    assert store.get(rid)["status"] == "PAUSING" and runtime.reservations()
    boot(client, auth, "boot-1", contribution=True, processes=[stopped(assignment)])
    store.dispatch_once()
    assert store.get(rid)["status"] == "PAUSED" and not runtime.reservations()
    assert store.get(rid)["pauseCheckpoint"] == checkpoint()


def test_resume_has_new_epoch_and_credentials_same_config_and_fences_old_reports(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    store.dispatch_once()
    old = runtime.runs()[0]
    frozen = copy.deepcopy(store.get(rid))
    with store.db() as db:
        old_body = json.loads(
            db.execute("SELECT body FROM assignments WHERE id=?", (old["assignmentId"],)).fetchone()[0]
        )
    boot(client, auth, "boot-1", contribution=True, reports=[paused_report(old)], processes=[stopped(old)])
    store.dispatch_once()
    for _ in range(2):
        assert client.post(f"/api/v1/experiments/{rid}/resume", headers=admin).status_code == 200
    store.dispatch_once()
    current = runtime.runs()[-1]
    assert current["assignmentId"] != old["assignmentId"] and current["epoch"] == old["epoch"] + 1
    with store.db() as db:
        new = json.loads(
            db.execute("SELECT body FROM assignments WHERE id=?", (current["assignmentId"],)).fetchone()[0]
        )
    assert new["config"] == old_body["config"]
    assert new["computeGrants"] != old_body["computeGrants"]
    assert new["resumeFrom"] == checkpoint()
    assert store.get(rid)["configHash"] == frozen["configHash"]
    assert store.get(rid)["completedGenerations"] == 1
    assert len(runtime.reservations()) == 1
    # Old sequence can be acknowledged for draining its durable outbox, but it
    # cannot overwrite the active epoch or a newer artifact projection.
    stale = paused_report(old, 100)
    stale["snapshot"]["state"] = {"status": "COMPLETED"}
    stale["snapshot"]["artifactContents"] = {"fake": "old"}
    boot(client, auth, "boot-1", contribution=True, reports=[stale], processes=[stopped(old)])
    assert runtime.snapshot(rid)["state"]["status"] == "STARTING"
    assert len(runtime.reservations()) == 1
    assert "artifactContents" not in store.snapshot(rid)
    assert all(
        c.get("assignmentId") != old["assignmentId"]
        for c in runtime.commands(device["deviceId"])
        if c["kind"] in ("COORDINATE", "START_WORKER", "PAUSE_ASSIGNMENT")
    )
    denied = client.post(
        "/api/v1/device/worker-command",
        headers=auth,
        json={
            "assignmentId": old["assignmentId"],
            "epoch": old["epoch"],
            "workerId": device["workerId"],
            "action": "start",
        },
    )
    assert denied.status_code == 403
    # All historical epochs survive a server restart.
    other = AgentRuntime()
    Store(store.path, {}, other)
    assert len(other.runs()) == 2 and other.snapshot(rid)["state"]["status"] == "STARTING"


def test_pause_without_verified_checkpoint_is_rejected_and_does_not_release(lab):
    client, store, runtime, _ = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    report = paused_report(assignment)
    report["snapshot"]["state"].pop("pauseCheckpoint")
    response = client.post(
        "/api/v1/device/poll",
        headers=auth,
        json={"bootId": "boot-1", "contribution": True, "reports": [report], "processes": [stopped(assignment)]},
    )
    assert response.status_code == 422 and runtime.reservations()


def test_paused_run_survives_contribution_off_and_resume_waits_for_owner_on(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    boot(
        client, auth, "boot-1", contribution=True, reports=[paused_report(assignment)], processes=[stopped(assignment)]
    )
    store.dispatch_once()
    assert (
        client.post(
            "/api/v1/devices/" + device["deviceId"] + "/contribution",
            headers=admin,
            json={"enabled": False, "bootId": "boot-1"},
        ).status_code
        == 200
    )
    boot(client, auth, "boot-1", contribution=False)
    assert store.get(rid)["status"] == "PAUSED"
    assert client.post(f"/api/v1/experiments/{rid}/resume", headers=admin).status_code == 200
    store.dispatch_once()
    assert store.get(rid)["status"] == "QUEUED"
    assert "ON" in store.get(rid)["waitingReason"]


@pytest.mark.parametrize("cancel_before_release", [False, True])
def test_cancellation_of_paused_or_pausing_run_never_requeues(lab, cancel_before_release):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    if cancel_before_release:
        client.post(f"/api/v1/experiments/{rid}/cancel", headers=admin)
    boot(
        client, auth, "boot-1", contribution=True, reports=[paused_report(assignment)], processes=[stopped(assignment)]
    )
    store.dispatch_once()
    if not cancel_before_release:
        client.post(f"/api/v1/experiments/{rid}/cancel", headers=admin)
    assert store.get(rid)["status"] == "CANCELLED" and not runtime.reservations()
    assert client.post(f"/api/v1/experiments/{rid}/resume", headers=admin).status_code == 409


@pytest.mark.parametrize("cancelled", [True, False])
def test_a_run_cancelled_before_its_coordinator_accepted_it_is_released(lab, cancelled):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    if cancelled:
        client.post(f"/api/v1/experiments/{rid}/cancel", headers=admin)
    # The agent never accepted COORDINATE (it was refused, then cancelled): no runner snapshot, nothing alive.
    boot(client, auth, "boot-1", contribution=True, processes=[stopped(assignment)])
    store.dispatch_once()
    if cancelled:
        assert store.get(rid)["status"] == "CANCELLED" and not runtime.reservations()
    else:  # without a cancel the lab keeps waiting for the coordinator; it never invents an outcome
        assert store.get(rid)["status"] == "STARTING" and runtime.reservations()
