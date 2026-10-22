"""Removing a device from the lab's list: only revoked or still-pending ones, never one that may be working."""

import uuid
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.devices import AgentRuntime
from labkit import login
from test_lab import register, activate
from labkit import boot, enable, pair, queued


def path(d):
    return "/api/v1/platform/devices/" + d["deviceId"]


def revoke(lab, d):
    c, s, r, a = lab
    assert c.patch(path(d), headers=a, json={"approved": False}).status_code == 200


def listed(lab):
    return {d["workerId"] for d in lab[2].devices()}


def test_a_revoked_device_can_be_removed_and_disappears(lab):
    c, s, r, a = lab
    d, h = pair(lab, "old-3060")
    revoke(lab, d)
    assert "old-3060" in listed(lab)
    assert c.delete(path(d), headers=a).status_code == 204
    assert "old-3060" not in listed(lab)
    assert c.delete(path(d), headers=a).status_code == 404, 'removing twice is a clear "not found"'


def test_the_device_credential_stops_working_after_removal(lab):
    c, s, r, a = lab
    d, h = pair(lab, "old-3060")
    revoke(lab, d)
    c.delete(path(d), headers=a)
    assert c.post("/api/v1/device/poll", headers=h, json={"bootId": "x"}).status_code == 401


def test_a_pending_device_can_be_declined_and_removed(lab):
    c, s, r, a = lab
    code = c.post("/api/v1/devices/pairing-codes", headers=a).json()["code"]
    data = {
        "code": code,
        "workerId": "pending-pc",
        "displayName": "pending",
        "selfTest": {
            "passed": True,
            "coordinator": False,
            "gpuName": "GPU",
            "vramTotalMb": 12000,
            "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
            "gpuUUID": "GPU-" + str(uuid.uuid5(uuid.NAMESPACE_DNS, "pending-pc")),
        },
        "computeUrl": "http://100.64.0.1:8769",
    }
    response = c.post("/api/v1/device/enroll", json=data)
    assert response.status_code == 201, response.text
    device = response.json()
    assert c.delete(path(device), headers=a).status_code == 204
    assert "pending-pc" not in listed(lab)


def test_an_approved_device_cannot_be_removed_until_it_is_revoked(lab):
    c, s, r, a = lab
    d, h = pair(lab, "working-pc")
    response = c.delete(path(d), headers=a)
    assert response.status_code == 409
    assert "working-pc" in listed(lab)


def test_a_quarantined_device_cannot_be_removed(lab):
    c, s, r, a = lab
    d, h = pair(lab, "quarantined-pc")
    with s.db() as db:
        db.execute('UPDATE devices SET status="QUARANTINED" WHERE id=?', (d["deviceId"],))
    response = c.delete(path(d), headers=a)
    assert response.status_code == 409
    assert "quarantine" in response.text.lower(), 'the owner is told why, not only "revoke first"'
    with s.db() as db:
        assert db.execute("SELECT 1 FROM devices WHERE id=?", (d["deviceId"],)).fetchone()


def test_a_device_that_still_holds_a_reservation_cannot_be_removed(lab):
    c, s, r, a = lab
    d, h = pair(lab, "busy-pc")
    revoke(lab, d)
    with s.db() as db:
        db.execute("INSERT INTO device_reservations VALUES (?,?)", (d["deviceId"], "assignment-1"))
    assert c.delete(path(d), headers=a).status_code == 409
    assert "busy-pc" in listed(lab)


def test_only_an_administrator_can_remove(lab):
    c, s, r, a = lab
    d, h = pair(lab, "old-3060")
    revoke(lab, d)
    assert c.delete(path(d)).status_code in (401, 403)
    assert c.delete(path(d), headers=h).status_code in (401, 403)
    profile, member = register(c, "alice")
    activate(c, a, profile)
    assert c.delete(path(d), headers=member).status_code == 403, "an ordinary signed-in user is not an administrator"
    assert "old-3060" in listed(lab)


def test_removal_is_written_to_the_audit_log_and_frees_the_worker_alias(lab):
    c, s, r, a = lab
    d, h = pair(lab, "old-3060")
    revoke(lab, d)
    with s.db() as db:
        db.execute("INSERT INTO device_commands VALUES ('c1',?,'dedupe-1','{}',0,1)", (d["deviceId"],))
        db.execute("INSERT INTO device_telemetry_history VALUES (?,'b',1,1,'{}')", (d["deviceId"],))
        db.execute("INSERT INTO device_reports VALUES (?,'a1',1)", (d["deviceId"],))
    c.delete(path(d), headers=a)
    with s.db() as db:
        actions = [row[0] for row in db.execute("SELECT action FROM audit WHERE target=?", (d["deviceId"],))]
    assert "DEVICE_REMOVED" in actions and "DEVICE_ENROLLED" in actions, "history is kept in the audit log"
    with s.db() as db:
        assert not db.execute("SELECT 1 FROM worker_assignments WHERE worker_id=?", ("old-3060",)).fetchone()
    with s.db() as db:
        for table in ("device_commands", "device_telemetry_history", "device_reports"):
            assert not db.execute(f"SELECT 1 FROM {table} WHERE device_id=?", (d["deviceId"],)).fetchone(), table
    pair(lab, "old-3060")  # the same alias can pair again
    assert "old-3060" in listed(lab)


def test_an_unknown_device_is_not_found(lab):
    c, s, r, a = lab
    assert c.delete("/api/v1/platform/devices/does-not-exist", headers=a).status_code == 404


def own(d):
    return "/api/v1/devices/" + d["deviceId"]


def test_an_approved_device_is_revoked_and_removed_in_one_step(lab):
    # owner 2026-10-22: "xoá thì vừa thu hồi vừa xoá luôn"
    c, s, r, a = lab
    d, h = pair(lab, "old-3060")
    assert c.delete(own(d), headers=a).status_code == 204
    assert "old-3060" not in listed(lab)
    assert c.post("/api/v1/device/poll", headers=h, json={"bootId": "x"}).status_code == 401
    with s.db() as db:
        actions = [row[0] for row in db.execute("SELECT action FROM audit WHERE target=?", (d["deviceId"],))]
    assert actions[-2:] == ["DEVICE_REVOKED", "DEVICE_REMOVED"]


def test_one_step_delete_never_cancels_a_run_nor_removes_a_quarantined_device(lab):
    c, s, r, a = lab
    d, h = pair(lab, "busy-pc")
    with s.db() as db:
        db.execute("INSERT INTO device_reservations VALUES (?,?)", (d["deviceId"], "assignment-1"))
    response = c.delete(own(d), headers=a)
    assert response.status_code == 409 and "OFF" in response.text
    with s.db() as db:
        assert db.execute("SELECT status FROM devices WHERE id=?", (d["deviceId"],)).fetchone()[0] == "APPROVED"
        db.execute("DELETE FROM device_reservations")
        db.execute('UPDATE devices SET status="QUARANTINED" WHERE id=?', (d["deviceId"],))
    assert c.delete(own(d), headers=a).status_code == 409
    assert "busy-pc" in listed(lab)


def test_the_owner_renames_and_deletes_its_device_and_nobody_else_can(lab):
    c, s, r, a = lab
    owner_profile, owner = register(c, "bob")
    activate(c, a, owner_profile)
    stranger_profile, stranger = register(c, "eve")
    activate(c, a, stranger_profile)
    code = c.post("/api/v1/devices/pairing-codes", headers=owner).json()["code"]
    data = {
        "code": code,
        "workerId": "bob-pc",
        "displayName": "DESKTOP-7Q3",
        "selfTest": {
            "passed": True,
            "coordinator": False,
            "gpuName": "GPU",
            "vramTotalMb": 12000,
            "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
            "gpuUUID": "GPU-" + str(uuid.uuid5(uuid.NAMESPACE_DNS, "bob-pc")),
        },
        "computeUrl": "http://100.64.0.1:8769",
    }
    device = c.post("/api/v1/device/enroll", json=data).json()
    assert c.patch(own(device), headers=stranger, json={"displayName": "mine"}).status_code == 404
    assert c.delete(own(device), headers=stranger).status_code == 404
    renamed = c.patch(own(device), headers=owner, json={"displayName": "  3060 phòng lab  "})
    assert renamed.status_code == 200 and renamed.json()["displayName"] == "3060 phòng lab"
    assert c.patch(own(device), headers=a, json={"displayName": "3060 Bob"}).status_code == 200, "the admin may too"
    assert {d["workerId"]: d["displayName"] for d in r.devices()}["bob-pc"] == "3060 Bob"
    assert c.delete(own(device), headers=owner).status_code == 204
    assert "bob-pc" not in listed(lab)
