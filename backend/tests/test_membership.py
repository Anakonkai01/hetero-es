"""
Elastic membership in the lab (ADR-009): a worker joins or leaves a running experiment. The same eligibility rules as at
submission apply, the device and its physical GPU are reserved, the coordinator gets one UPDATE_MEMBERSHIP command with the
worker's own credential, and every change is audited. The frozen configuration never changes.
"""

import json
import time

from backend.agent_scheduling import LEFT_OFFLINE_RELEASE_SECONDS
from labkit import boot, draft, enable, pair


def running(lab, workers=1, extra=0, **changes):
    """A coordinator, `workers` workers in the experiment and `extra` idle workers, all ON; the run is dispatched."""
    client, store, runtime, admin = lab
    coordinator, ch = pair(lab, "coordinator")
    enable(lab, coordinator, ch)
    devices = []
    for index in range(workers + extra):
        device, auth = pair(lab, f"gpu-{index}", False)
        enable(lab, device, auth)
        devices.append((device, auth))
    body = {"workerIds": [d["workerId"] for d, _ in devices[:workers]], "coordinatorDeviceId": coordinator["deviceId"]}
    r = draft(client, admin, **body, **changes)
    assert r.status_code == 200, r.text
    rid = r.json()["experimentId"]
    assert client.post(f"/api/v1/experiments/{rid}/submit", headers=admin).status_code == 200
    store.dispatch_once()
    return rid, (coordinator, ch), devices


def change(lab, rid, worker_id, action="add", headers=None):
    client, _, _, admin = lab
    return client.post(
        f"/api/v1/experiments/{rid}/workers", json={"workerId": worker_id, "action": action}, headers=headers or admin
    )


def assignment_body(store, rid):
    with store.db() as db:
        row = db.execute("SELECT body FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (rid,)).fetchone()
        return json.loads(row[0])


def membership_commands(runtime, coordinator):
    return [c for c in runtime.commands(coordinator["deviceId"]) if c["kind"] == "UPDATE_MEMBERSHIP"]


def test_a_worker_joins_a_running_experiment_with_its_own_credential_and_reservation(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    late = devices[1][0]
    before = store.get(rid)["configHash"]
    reply = change(lab, rid, late["workerId"])
    assert reply.status_code == 200, reply.text
    assert reply.json()["action"] == "JOIN" and reply.json()["appliesAtNextGeneration"] is True
    [command] = membership_commands(runtime, coordinator)
    joined = command["change"]
    assert (joined["workerId"], joined["action"], joined["actor"]) == (late["workerId"], "JOIN", "admin")
    assignment = assignment_body(store, rid)
    assert joined["grant"] == assignment["computeGrants"][late["workerId"]]
    assert joined["grant"] not in {v for k, v in assignment["computeGrants"].items() if k != late["workerId"]}
    assert assignment["workerDevices"][late["workerId"]] == late["deviceId"]
    assert {"deviceId": late["deviceId"], "assignmentId": assignment["assignmentId"]} in runtime.reservations()
    assert store.get(rid)["configHash"] == before and store.get(rid)["workerIds"] == [devices[0][0]["workerId"]]
    # the coordinator may now start the new worker through the ordinary lifecycle command
    start = client.post(
        "/api/v1/device/worker-command",
        headers=ch,
        json={
            "assignmentId": assignment["assignmentId"],
            "epoch": assignment["epoch"],
            "workerId": late["workerId"],
            "action": "start",
            "recoveryIndex": 0,
        },
    )
    assert start.status_code == 200, start.text
    assert [r["workerId"] for r in store.get(rid)["membershipRequests"]] == [late["workerId"]]
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM audit WHERE action='MEMBERSHIP_JOIN_REQUESTED'").fetchone()[0] == 1
    assert change(lab, rid, late["workerId"]).status_code == 409  # already a member


def test_a_worker_leaves_but_the_last_one_cannot(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    first, second = devices[0][0], devices[1][0]
    assert change(lab, rid, first["workerId"], "remove").status_code == 200
    assert membership_commands(runtime, coordinator)[-1]["change"]["action"] == "LEAVE"
    assert "grant" not in membership_commands(runtime, coordinator)[-1]["change"]
    reply = change(lab, rid, second["workerId"], "remove")
    assert reply.status_code == 409 and "last" in reply.json()["message"]
    assert change(lab, rid, first["workerId"], "remove").status_code == 409  # it is no longer a member


def test_joining_follows_the_rules_of_submission(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    off, off_auth = devices[1]
    client.post(
        "/api/v1/devices/" + off["deviceId"] + "/contribution",
        headers=admin,
        json={"enabled": False, "bootId": "boot-1"},
    )
    reply = change(lab, rid, off["workerId"])
    assert reply.status_code == 409 and "contribution" in reply.json()["message"]
    assert change(lab, rid, coordinator["workerId"]).status_code == 409  # the coordinator itself is not a worker here
    assert change(lab, rid, "nobody").status_code == 409
    assert change(lab, rid, devices[0][0]["workerId"], "dance").status_code == 422
    assert membership_commands(runtime, coordinator) == []


def test_a_device_busy_in_another_experiment_cannot_join(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    other, other_auth = pair(lab, "other-coordinator")
    enable(lab, other, other_auth)
    busy = devices[1][0]
    r = draft(client, admin, workerIds=[busy["workerId"]], coordinatorDeviceId=other["deviceId"])
    second = r.json()["experimentId"]
    client.post(f"/api/v1/experiments/{second}/submit", headers=admin)
    store.dispatch_once()
    reply = change(lab, rid, busy["workerId"])
    assert reply.status_code == 409 and "release" in reply.json()["message"]


def test_only_the_owner_or_an_administrator_changes_members_and_only_while_it_runs(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    client.post("/api/v1/platform/users", headers=admin, json={"username": "someone", "password": "someone-pass-1"})
    draft_only = draft(
        client, admin, workerIds=[devices[0][0]["workerId"]], coordinatorDeviceId=coordinator["deviceId"]
    )
    reply = change(lab, draft_only.json()["experimentId"], devices[1][0]["workerId"])
    assert reply.status_code == 409 and "running" in reply.json()["message"]
    assert client.post(f"/api/v1/experiments/{rid}/workers", json={"workerId": "x", "action": "add"}).status_code == 401


def test_a_coordinator_without_membership_support_is_told_to_update(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    old = {**ch, "X-HeteroES-Agent-Commands": "SET_CONTRIBUTION,COORDINATE,START_WORKER,STOP_WORKER,CANCEL_ASSIGNMENT"}
    boot(client, old, "boot-1", contribution=True)
    reply = change(lab, rid, devices[1][0]["workerId"])
    assert reply.status_code == 409 and "Update" in reply.json()["message"]


def test_a_left_worker_releases_its_gpu_once_the_coordinator_confirms_it_stopped(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    first = devices[0][0]
    assert change(lab, rid, first["workerId"], "remove").status_code == 200
    assignment = assignment_body(store, rid)

    def report(sequence, alive):
        return {
            "sequence": sequence,
            "assignmentId": assignment["assignmentId"],
            "epoch": assignment["epoch"],
            "snapshot": {
                "state": {
                    "status": "RUNNING",
                    "workerStates": {first["workerId"]: {"alive": alive, "confirmed": True}},
                },
                "membership": {"generation": 4, "members": [devices[1][0]["workerId"]], "left": [first["workerId"]]},
                "generations": [],
                "candidates": [],
                "attempts": [],
                "events": [],
                "artifacts": [],
            },
        }

    boot(client, ch, "boot-1", contribution=True, reports=[report(1, True)])
    assert any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())  # still running its last work
    boot(client, ch, "boot-1", contribution=True, reports=[report(2, False)])
    assert not any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())
    assert first["workerId"] not in assignment_body(store, rid)["workerDevices"]  # not waited for at the final release
    store.dispatch_once()
    assert store.get(rid)["membership"]["left"] == [first["workerId"]]
    assert store.get(rid)["status"] not in ("CANCELLED", "CANCELLING")
    # c8 run, 2026-10-21: added back, its next report still says "left" until the coordinator's next boundary; that old
    # view released it again, so the coordinator was refused when it asked to start it
    assert change(lab, rid, first["workerId"]).status_code == 200
    boot(client, ch, "boot-1", contribution=True, reports=[report(3, False)])
    assert first["workerId"] in assignment_body(store, rid)["workerDevices"]
    assert any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())
    assignment = assignment_body(store, rid)
    probe = client.post(
        "/api/v1/device/worker-command",
        headers=ch,
        json={
            "assignmentId": assignment["assignmentId"],
            "epoch": assignment["epoch"],
            "workerId": first["workerId"],
            "action": "probe",
            "recoveryIndex": 0,
        },
    )
    assert probe.status_code == 200, probe.text


def test_a_left_worker_that_went_offline_releases_its_gpu_after_a_grace_period(lab):
    # GSM8K demo tier 2, 2026-10-21: quang-3060 left and its machine died; it could never confirm the stop, so the finished
    # run stayed DRAINING and held every device until the machine came back 40 minutes later
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    first = devices[0][0]
    assert change(lab, rid, first["workerId"], "remove").status_code == 200
    assignment = assignment_body(store, rid)
    snapshot = {
        "state": {"status": "COMPLETED", "workerStates": {first["workerId"]: {"alive": True, "confirmed": False}}},
        "membership": {"generation": 4, "members": [devices[1][0]["workerId"]], "left": [first["workerId"]]},
        "generations": [],
        "candidates": [],
        "attempts": [],
        "events": [],
        "artifacts": [],
    }
    report = {"sequence": 1, "assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"], "snapshot": snapshot}
    boot(client, ch, "boot-1", contribution=True, reports=[report])
    assert any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())  # just seen: it may still be working

    def offline_for(seconds):
        with store.db() as db:
            db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time() - seconds, first["deviceId"]))

    offline_for(LEFT_OFFLINE_RELEASE_SECONDS - 60)
    boot(client, ch, "boot-1", contribution=True)
    assert any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())
    offline_for(LEFT_OFFLINE_RELEASE_SECONDS + 1)
    boot(client, ch, "boot-1", contribution=True)  # no new report: the coordinator has nothing more to say
    assert not any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())
    body = assignment_body(store, rid)
    assert first["workerId"] not in body["workerDevices"] and first["deviceId"] not in body["deviceIds"]
    # it was only cut off: back online with its worker still running, it is told to stop it before anything else
    process = {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"], "workerAlive": True}
    reply = boot(client, devices[0][1], "boot-1", contribution=True, processes=[process])
    assert reply["revokedAssignments"] == [assignment["assignmentId"]]
    reply = boot(client, devices[1][1], "boot-1", contribution=True, processes=[process])
    assert reply["revokedAssignments"] == []  # the member still in the run keeps its worker


def test_a_finished_run_is_released_when_a_member_machine_died_without_leaving(lab):
    # GSM8K demo tier 2b, 2026-10-21: the 1660S died during the run (no OFF, no LEAVE). The coordinator finished and
    # counted it stopped; the lab still waited for the dead machine to report, so every device stayed reserved.
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    (dead, _), (live, live_auth) = devices
    assignment = assignment_body(store, rid)
    gone = {"alive": False, "confirmed": False}

    def finish(sequence, dead_state):
        snapshot = {
            "state": {
                "status": "COMPLETED",
                "workerStates": {dead["workerId"]: dead_state, live["workerId"]: {"alive": False, "confirmed": True}},
            },
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": [],
            "artifacts": [],
        }
        report = {"sequence": sequence, "assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"]}
        stopped = {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"]}
        boot(client, live_auth, "boot-1", contribution=True, processes=[{**stopped, "workerAlive": False}])
        boot(
            client,
            ch,
            "boot-1",
            contribution=True,
            reports=[{**report, "snapshot": snapshot}],
            processes=[{**stopped, "coordinatorAlive": False}],
        )

    with store.db() as db:
        db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time() - LEFT_OFFLINE_RELEASE_SECONDS - 1, dead["deviceId"]))
    finish(1, gone)
    assert runtime.reservations()  # the coordinator has not counted it stopped: it may still be working
    finish(2, {"alive": False, "confirmed": True, "lost": True})
    assert not runtime.reservations()
    with store.db() as db:
        db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time(), dead["deviceId"]))
    # back with its worker still alive: the release is announced and the process is revoked
    process = {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"], "workerAlive": True}
    reply = boot(client, devices[0][1], "boot-1", contribution=True, processes=[process])
    assert assignment["assignmentId"] in reply["releasedAssignments"]
    assert reply["revokedAssignments"] == [assignment["assignmentId"]]


def test_a_finished_run_waits_for_a_member_that_is_only_briefly_offline(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    (dead, _), (live, live_auth) = devices
    assignment = assignment_body(store, rid)
    with store.db() as db:
        db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time() - 120, dead["deviceId"]))
    snapshot = {
        "state": {
            "status": "COMPLETED",
            "workerStates": {w["workerId"]: {"alive": False, "confirmed": True} for w in (dead, live)},
        },
        "generations": [],
        "candidates": [],
        "attempts": [],
        "events": [],
        "artifacts": [],
    }
    stopped = {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"]}
    boot(client, live_auth, "boot-1", contribution=True, processes=[{**stopped, "workerAlive": False}])
    report = {"sequence": 1, **stopped, "snapshot": snapshot}
    boot(client, ch, "boot-1", contribution=True, reports=[report], processes=[{**stopped, "coordinatorAlive": False}])
    assert runtime.reservations()


def test_an_offline_worker_that_did_not_leave_keeps_its_reservation(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    first = devices[0][0]
    with store.db() as db:
        db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time() - 3600, first["deviceId"]))
    boot(client, ch, "boot-1", contribution=True)
    assert any(r["deviceId"] == first["deviceId"] for r in runtime.reservations())  # a member is waited for (restart)


def test_turning_a_member_off_makes_it_leave_instead_of_cancelling_the_experiment(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    first = devices[0][0]
    client.post(
        "/api/v1/devices/" + first["deviceId"] + "/contribution",
        headers=admin,
        json={"enabled": False, "bootId": "boot-1"},
    )
    assert not store.get(rid).get("cancelRequested")
    [command] = membership_commands(runtime, coordinator)
    assert (command["change"]["workerId"], command["change"]["action"], command["change"]["actor"]) == (
        first["workerId"],
        "LEAVE",
        "system",
    )


def test_turning_a_member_off_sends_no_cancellation_to_anyone(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2)
    first = devices[0][0]
    client.post(
        "/api/v1/devices/" + first["deviceId"] + "/contribution",
        headers=admin,
        json={"enabled": False, "bootId": "boot-1"},
    )
    everyone = [coordinator, *[d for d, _ in devices]]
    assert not [c for d in everyone for c in runtime.commands(d["deviceId"]) if c["kind"] == "CANCEL_ASSIGNMENT"]


def test_turning_the_last_member_off_still_cancels(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1)
    only = devices[0][0]
    client.post(
        "/api/v1/devices/" + only["deviceId"] + "/contribution",
        headers=admin,
        json={"enabled": False, "bootId": "boot-1"},
    )
    assert store.get(rid).get("cancelRequested") is True
    assert membership_commands(runtime, coordinator) == []


def test_an_experiment_that_allows_joining_takes_an_idle_eligible_worker_by_itself(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1, allowJoin=True)
    store.dispatch_once()
    [command] = membership_commands(runtime, coordinator)
    assert (command["change"]["workerId"], command["change"]["actor"]) == (devices[1][0]["workerId"], "system")
    store.dispatch_once()  # not twice
    assert len(membership_commands(runtime, coordinator)) == 1


def test_a_worker_its_owner_removed_is_not_taken_back_by_itself(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=2, allowJoin=True)
    removed = devices[1][0]
    assert change(lab, rid, removed["workerId"], "remove").status_code == 200
    assignment = assignment_body(store, rid)
    gone = {
        "sequence": 1,
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "snapshot": {
            "state": {"status": "RUNNING", "workerStates": {removed["workerId"]: {"alive": False, "left": True}}},
            "membership": {"members": [devices[0][0]["workerId"]], "left": [removed["workerId"]]},
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": [],
            "artifacts": [],
        },
    }
    boot(client, ch, "boot-1", contribution=True, reports=[gone])  # its GPU is free again, and it is still ON
    assert not any(r["deviceId"] == removed["deviceId"] for r in runtime.reservations())
    store.dispatch_once()
    store.dispatch_once()
    actions = [(c["change"]["workerId"], c["change"]["action"]) for c in membership_commands(runtime, coordinator)]
    assert actions == [(removed["workerId"], "LEAVE")]


def test_without_allow_join_nothing_joins_by_itself(lab):
    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    store.dispatch_once()
    assert membership_commands(runtime, coordinator) == []
    assert store.get(rid)["allowJoin"] is False


def test_a_resumed_experiment_keeps_the_workers_that_joined(lab):
    from test_pause_resume import paused_report, stopped

    client, store, runtime, admin = lab
    rid, (coordinator, ch), devices = running(lab, workers=1, extra=1)
    (first, first_auth), (late, late_auth) = devices
    assert change(lab, rid, late["workerId"]).status_code == 200
    old = runtime.runs()[0]
    assert client.post(f"/api/v1/experiments/{rid}/pause", headers=admin).status_code == 200
    boot(client, ch, "boot-1", contribution=True, reports=[paused_report(old)], processes=[stopped(old)])
    for auth in (first_auth, late_auth):
        boot(client, auth, "boot-1", contribution=True, processes=[stopped(old)])
    store.dispatch_once()
    assert store.get(rid)["status"] == "PAUSED"
    assert client.post(f"/api/v1/experiments/{rid}/resume", headers=admin).status_code == 200
    store.dispatch_once()
    resumed = assignment_body(store, rid)
    assert resumed["epoch"] == old["epoch"] + 1
    assert set(resumed["workerDevices"]) == {first["workerId"], late["workerId"]}
    assert resumed["computeGrants"][late["workerId"]] and resumed["config"]["workerIds"] == [first["workerId"]]
