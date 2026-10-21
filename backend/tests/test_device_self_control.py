"""The machine's own command line (owner decisions 2026-10-22): an approved device turns itself ON or OFF with its own
token, the owner may keep a device contributing after it restarts, and the device reads a summary of itself."""

from labkit import boot, enable, pair


def commands(lab, device, kind="SET_CONTRIBUTION"):
    _, _, runtime, _ = lab
    return [c for c in runtime.commands(device["deviceId"]) if c["kind"] == kind]


def test_an_approved_device_turns_itself_on_and_off_and_the_audit_names_it(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    boot(client, auth, "boot-1")
    r = client.post("/api/v1/device/contribution", headers=auth, json={"enabled": True})
    assert r.status_code == 200, r.text
    assert commands(lab, device)[-1] | {"commandId": None} == {
        "commandId": None,
        "kind": "SET_CONTRIBUTION",
        "enabled": True,
        "bootId": "boot-1",
    }
    assert boot(client, auth, "boot-1", contribution=True)["desiredContribution"] is True
    assert client.post("/api/v1/device/contribution", headers=auth, json={"enabled": False}).status_code == 200
    assert boot(client, auth, "boot-1")["desiredContribution"] is False
    with store.db() as db:
        actors = [r[0] for r in db.execute("SELECT actor FROM audit WHERE action IN ('DEVICE_ON','DEVICE_OFF')")]
    assert actors[-2:] == ["device:" + device["deviceId"]] * 2


def test_a_device_that_is_not_approved_or_unknown_cannot_turn_itself_on(lab):
    client, store, _, _ = lab
    device, auth = pair(lab)
    boot(client, auth, "boot-1")
    with store.db() as db:
        db.execute("UPDATE devices SET status='PENDING' WHERE id=?", (device["deviceId"],))
    assert client.post("/api/v1/device/contribution", headers=auth, json={"enabled": True}).status_code == 409
    stranger = {"Authorization": "Bearer not-a-device"}
    assert client.post("/api/v1/device/contribution", headers=stranger, json={"enabled": True}).status_code == 401


def test_every_boot_starts_off_unless_the_owner_chose_to_keep_it_on(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    assert boot(client, auth, "boot-2")["desiredContribution"] is False  # the default: a restart turns it OFF
    r = client.post(
        f"/api/v1/devices/{device['deviceId']}/contribution",
        headers=admin,
        json={"enabled": True, "bootId": "boot-2", "keepAfterReboot": True},
    )
    assert r.status_code == 200, r.text
    assert runtime.devices()[0]["keepContributionAfterReboot"] is True
    assert boot(client, auth, "boot-3")["desiredContribution"] is True
    reply = boot(client, auth, "boot-3")  # commands queued during a poll are delivered by the next one
    assert [(c["enabled"], c["bootId"]) for c in reply["commands"] if c["kind"] == "SET_CONTRIBUTION"] == [(True, "boot-3")]
    assert boot(client, auth, "boot-3", contribution=True)["desiredContribution"] is True
    # the device itself can drop the choice
    client.post("/api/v1/device/contribution", headers=auth, json={"enabled": False, "keepAfterReboot": False})
    assert boot(client, auth, "boot-4")["desiredContribution"] is False


def test_the_device_reads_its_own_summary(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    r = client.get("/api/v1/device/summary", headers=auth)
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["deviceId"] == device["deviceId"] and summary["approvalStatus"] == "APPROVED"
    assert summary["contributionEnabled"] is True and summary["keepContributionAfterReboot"] is False
    assert summary["runs"] == []
    assert client.get("/api/v1/device/summary", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_the_owner_sets_keep_on_without_touching_the_current_boot(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    path = f"/api/v1/devices/{device['deviceId']}/contribution"
    before = commands(lab, device)
    assert client.patch(path, headers=admin, json={"keepAfterReboot": True}).status_code == 200
    assert runtime.devices()[0]["contributionEnabled"] is True  # still ON, no command queued
    assert commands(lab, device) == before
    assert boot(client, auth, "boot-2")["desiredContribution"] is True
