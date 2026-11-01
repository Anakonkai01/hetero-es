"""Independent device guards survive extraction, including inputs that bypass other rejection reasons."""

import hashlib
import json
import time

import pytest

from backend.core.errors import ServiceError
from backend.services.devices import operations
from labkit import boot, enable, pair, queued
from test_pause_resume import paused_report, stopped


def enrollment(code, alias):
    return {
        "code": code,
        "workerId": alias,
        "displayName": alias,
        "computeUrl": "http://100.64.0.1:8769",
        "selfTest": {
            "passed": True,
            "gpuName": "CPU fixture profile",
            "vramTotalMb": 12000,
            "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
        },
    }


def test_expired_unused_pairing_code_cannot_enroll_a_new_alias(lab):
    client, store, _, owner = lab
    code = client.post("/api/v1/devices/pairing-codes", headers=owner).json()["code"]
    with store.db() as db:
        db.execute("UPDATE pairing_codes SET expires=?", (time.time() - 60,))
    response = client.post("/api/v1/device/enroll", json=enrollment(code, "new-alias"))
    assert response.status_code == 409
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM devices").fetchone()[0] == 0
    fresh = client.post("/api/v1/devices/pairing-codes", headers=owner).json()["code"]
    assert client.post("/api/v1/device/enroll", json=enrollment(fresh, "new-alias")).status_code == 201


def test_consumed_pairing_code_cannot_enroll_a_different_alias(lab):
    client, store, _, owner = lab
    code = client.post("/api/v1/devices/pairing-codes", headers=owner).json()["code"]
    assert client.post("/api/v1/device/enroll", json=enrollment(code, "first-alias")).status_code == 201
    assert client.post("/api/v1/device/enroll", json=enrollment(code, "different-alias")).status_code == 409
    with store.db() as db:
        assert [r[0] for r in db.execute("SELECT worker_id FROM devices")] == ["first-alias"]


@pytest.mark.parametrize("status", ["REVOKED", "QUARANTINED"])
def test_restricted_device_may_drain_but_cannot_read_or_change_its_control_state(lab, status):
    client, store, _, _ = lab
    device, auth = pair(lab)
    with store.db() as db:
        db.execute("UPDATE devices SET status=? WHERE id=?", (status, device["deviceId"]))
    assert client.get("/api/v1/device/summary", headers=auth).status_code == 401
    assert client.patch("/api/v1/device/name", headers=auth, json={"displayName": "unauthorized"}).status_code == 401
    assert boot(client, auth, "boot-1")["desiredContribution"] is False
    with store.db() as db:
        assert db.execute("SELECT name FROM devices WHERE id=?", (device["deviceId"],)).fetchone()[0] != "unauthorized"


def test_another_approved_coordinator_cannot_command_a_selected_worker(lab):
    client, store, runtime, _ = lab
    device, auth = pair(lab)
    _, attacker_auth = pair(lab, "another-coordinator")
    enable(lab, device, auth)
    queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    body = {
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "workerId": device["workerId"],
        "action": "start",
    }
    before = runtime.commands(device["deviceId"])
    assert client.post("/api/v1/device/worker-command", headers=attacker_auth, json=body).status_code == 403
    assert runtime.commands(device["deviceId"]) == before
    assert client.post("/api/v1/device/worker-command", headers=auth, json=body).status_code == 200
    assert any(command["kind"] == "START_WORKER" for command in runtime.commands(device["deviceId"]))


def test_well_formed_but_unverified_pause_checkpoint_cannot_release_ownership(lab):
    client, store, runtime, _ = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    run = queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    report = paused_report(assignment)
    report["snapshot"]["state"]["pauseCheckpoint"]["verified"] = False
    payload = {"bootId": "boot-1", "contribution": True, "reports": [report], "processes": [stopped(assignment)]}
    assert client.post("/api/v1/device/poll", headers=auth, json=payload).status_code == 422
    assert runtime.snapshot(run)["state"]["status"] == "STARTING" and runtime.reservations()
    report["snapshot"]["state"]["pauseCheckpoint"]["verified"] = True
    assert client.post("/api/v1/device/poll", headers=auth, json=payload).status_code == 200
    assert runtime.snapshot(run)["state"]["status"] == "PAUSED" and not runtime.reservations()


def test_monitoring_event_hash_binds_the_exact_payload(lab):
    client, store, runtime, _ = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    queued(lab, device)
    store.dispatch_once()
    assignment = runtime.runs()[0]
    event = {"event": "generation_done", "generation": 0, "t": 100}
    event_id = hashlib.sha256(
        (assignment["assignmentId"] + json.dumps(event, sort_keys=True, separators=(",", ":"))).encode()
    ).hexdigest()
    envelope = {
        "eventId": event_id,
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "event": event,
    }
    changed = {**envelope, "event": {**event, "generation": 99}}
    assert boot(client, auth, "boot-1", contribution=True, events=[changed])["acceptedEvents"] == []
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM monitoring_events").fetchone()[0] == 0
    assert boot(client, auth, "boot-1", contribution=True, events=[envelope])["acceptedEvents"] == [event_id]


def test_old_stopped_process_report_does_not_release_a_newly_completed_assignment(lab):
    client, store, runtime, _ = lab
    coordinator, coordinator_auth = pair(lab)
    worker, worker_auth = pair(lab, "separate-worker", coordinator=False)
    enable(lab, coordinator, coordinator_auth)
    enable(lab, worker, worker_auth)
    run = queued(lab, coordinator, workerIds=[worker["workerId"]])
    store.dispatch_once()
    assignment = runtime.runs()[0]
    boot(client, worker_auth, "boot-1", contribution=True, processes=[stopped(assignment)])
    with store.db() as db:
        db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time() - 60, worker["deviceId"]))
    report = paused_report(assignment)
    report["snapshot"]["state"] = {"status": "COMPLETED"}
    boot(
        client,
        coordinator_auth,
        "boot-1",
        contribution=True,
        reports=[report],
        processes=[stopped(assignment)],
    )
    assert runtime.snapshot(run)["state"]["status"] == "DRAINING"
    assert {r["deviceId"] for r in runtime.reservations()} == {coordinator["deviceId"], worker["deviceId"]}
    boot(client, worker_auth, "boot-1", contribution=True, processes=[stopped(assignment)])
    assert runtime.snapshot(run)["state"]["status"] == "COMPLETED" and not runtime.reservations()


def test_device_service_authentication_failure_is_independent_of_http(lab):
    _, store, runtime, _ = lab
    service = operations(store, None, runtime)
    with pytest.raises(ServiceError) as missing:
        service.authenticate_device("missing-fixture-credential", "control")
    assert missing.value.status_code == 401
    assert not any(base.__module__.startswith(("fastapi", "starlette")) for base in type(missing.value).__mro__)
