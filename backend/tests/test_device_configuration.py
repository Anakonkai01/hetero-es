"""Role and route changes are one guarded CPU-only transaction."""

import json
import pytest
from labkit import boot, enable, pair, queued


def configuration(lab, device):
    _, _, runtime, _ = lab
    profile = next(d["selfTest"] for d in runtime.devices() if d["deviceId"] == device["deviceId"])
    return {"computeUrl": "http://192.168.1.8:8765", "selfTest": {**profile, "coordinator": True}}


def test_configuration_updates_role_and_endpoints_atomically(lab):
    client, store, runtime, owner = lab
    device, _ = pair(lab, coordinator=False)
    body = configuration(lab, device)
    response = client.patch(f"/api/v1/devices/{device['deviceId']}/configuration", headers=owner, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["computeUrl"] == body["computeUrl"]
    assert result["selfTest"]["coordinator"] is True
    assert result["contributionEnabled"] is False
    assert runtime.reservations() == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", False),
        ("gpuUUID", "GPU-00000000-0000-0000-0000-000000000000"),
        ("platform", "windows"),
        ("vramTotalMb", 0),  # any GPU may coordinate (owner, 2026-10-20), but a GPU profile needs VRAM
    ],
)
def test_invalid_role_or_identity_cannot_partially_change_endpoint(lab, field, value):
    client, _, runtime, owner = lab
    device, _ = pair(lab, coordinator=False)
    before = runtime.devices()[0]
    body = configuration(lab, device)
    body["selfTest"][field] = value
    response = client.patch(f"/api/v1/devices/{device['deviceId']}/configuration", headers=owner, json=body)
    assert response.status_code == 422, response.text
    after = runtime.devices()[0]
    assert (after["computeUrl"], after["selfTest"]) == (before["computeUrl"], before["selfTest"])


@pytest.mark.parametrize("condition", ["enabled", "desired", "reserved", "physical", "unknown", "alive"])
def test_configuration_refuses_live_or_uncertain_ownership(lab, condition):
    client, store, runtime, owner = lab
    device, auth = pair(lab)
    if condition in ("enabled", "desired", "reserved", "physical"):
        enable(lab, device, auth)
        if condition in ("reserved", "physical"):
            queued(lab, device)
            store.dispatch_once()
            with store.db() as db:
                db.execute("UPDATE devices SET enabled=0,desired=0")
                if condition == "physical":
                    db.execute("DELETE FROM device_reservations")
        elif condition == "desired":
            with store.db() as db:
                db.execute("UPDATE devices SET enabled=0")
    else:
        processes = [
            {
                "assignmentId": "a" * 32,
                "epoch": 1,
                "workerAlive": None if condition == "unknown" else True,
                "coordinatorAlive": False,
                "ready": False,
            }
        ]
        with store.db() as db:
            db.execute("UPDATE devices SET processes=?", (json.dumps(processes),))
    before = runtime.devices()[0]
    response = client.patch(
        f"/api/v1/devices/{device['deviceId']}/configuration", headers=owner, json=configuration(lab, device)
    )
    assert response.status_code == 409, response.text
    after = runtime.devices()[0]
    assert (after["computeUrl"], after["selfTest"]) == (before["computeUrl"], before["selfTest"])


def test_configuration_requires_owner_session_and_health_advertises_it(lab):
    client, _, _, _ = lab
    device, auth = pair(lab)
    assert client.get("/api/v1/health").json()["deviceConfiguration"] is True
    route = f"/api/v1/devices/{device['deviceId']}/configuration"
    assert client.patch(route, headers=auth, json=configuration(lab, device)).status_code == 401
    assert client.patch(route, json=configuration(lab, device)).status_code == 401
