"""CPU-only protocol contracts; no runtime or CUDA import is allowed here."""

import hashlib
import json
from pathlib import Path
import time
import uuid
import pytest
from backend.devices import AgentRuntime
from labkit import boot, draft, enable, login, pair, pending_commands, queued, submitted  # noqa: F401  (fixtures lab and setup: conftest.py)


def test_poll_returns_the_current_boot_owner_contribution_choice(lab):
    client, _, _, owner = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    assert boot(client, auth, "boot-1", contribution=True)["desiredContribution"] is True
    response = client.post(
        "/api/v1/devices/" + device["deviceId"] + "/contribution",
        headers=owner,
        json={"enabled": False, "bootId": "boot-1"},
    )
    assert response.status_code == 200
    assert boot(client, auth, "boot-1", contribution=True)["desiredContribution"] is False


def test_offline_queue_and_boot_activation_are_independent(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    rid = queued(lab, d)
    s.dispatch_once()
    assert s.get(rid)["status"] == "QUEUED"
    assert r.runs() == []
    enable(lab, d, h)
    s.dispatch_once()
    assert s.get(rid)["status"] == "STARTING"
    assert len(r.runs()) == 1
    boot(c, h, "boot-2")
    assert (
        c.post(
            "/api/v1/devices/" + d["deviceId"] + "/contribution", headers=a, json={"enabled": True, "bootId": "boot-1"}
        ).status_code
        == 409
    )
    assert not r.devices()[0]["contributionEnabled"]


def test_assignment_is_idempotent_and_outage_never_releases(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    first, second = queued(lab, d), queued(lab, d, name="Second run")
    s.dispatch_once()
    s.dispatch_once()
    assignment = r.runs()[0]
    with s.db() as db:
        db.execute("UPDATE devices SET seen=0")
    s.dispatch_once()
    assert s.get(second)["status"] == "QUEUED"
    assert r.runs()[0]["assignmentId"] == assignment["assignmentId"]
    assert len(r.reservations()) == 1
    assert len([x for x in r.commands(d["deviceId"]) if x["kind"] == "COORDINATE"]) == 1


def test_terminal_snapshot_needs_all_process_death_and_fresh_epoch(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    rid = queued(lab, d)
    s.dispatch_once()
    assignment = r.runs()[0]
    report = {
        "sequence": 1,
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "snapshot": {
            "state": {"status": "COMPLETED"},
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": [],
            "artifacts": [],
            "completedGenerationCount": 3,
            "monitoringPartial": True,
            "latestGeneration": {"generationId": "g2", "committedCandidateCount": 8, "modelVersion": "final"},
        },
    }
    boot(c, h, "boot-1", contribution=True, reports=[{**report, "epoch": 99}])
    assert r.snapshot(rid)["state"]["status"] == "STARTING"
    boot(c, h, "boot-1", contribution=True, reports=[report])
    s.dispatch_once()
    assert s.get(rid)["status"] == "DRAINING"
    assert r.reservations()
    boot(
        c,
        h,
        "boot-1",
        contribution=True,
        processes=[
            {
                "assignmentId": assignment["assignmentId"],
                "epoch": assignment["epoch"],
                "coordinatorAlive": False,
                "workerAlive": False,
            }
        ],
        reports=[report],
    )
    s.dispatch_once()
    assert s.get(rid)["status"] == "COMPLETED"
    assert s.get(rid)["completedGenerations"] == 3
    assert s.get(rid)["currentGenerationId"] == "g2"
    assert not r.reservations()
    enriched = {
        **report,
        "sequence": 2,
        "snapshot": {
            **report["snapshot"],
            "state": {"status": "FAILED"},
            "artifactContents": {"config.json": {"base64": "e30=", "sha256": "unused"}},
        },
    }
    boot(c, h, "boot-1", reports=[enriched])
    assert s.get(rid)["status"] == "COMPLETED"
    assert s.snapshot(rid)["state"]["status"] == "COMPLETED"
    assert "config.json" in s.snapshot(rid)["artifactContents"]


def test_pairing_expiry_alias_collision_and_revocation(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    assert c.post("/api/v1/device/poll", json={"bootId": "x"}).status_code == 401
    assert (
        c.patch(
            "/api/v1/platform/devices/" + d["deviceId"], headers=a, json={"approved": False, "workspaceId": "lab"}
        ).status_code
        == 200
    )
    drained = c.post("/api/v1/device/poll", headers=h, json={"bootId": "x"})
    assert drained.status_code == 200 and not drained.json()["desiredContribution"]
    assert (
        c.post(
            "/api/v1/device/worker-command",
            headers=h,
            json={"assignmentId": "x", "epoch": 1, "workerId": "x", "action": "poll"},
        ).status_code
        == 401
    )
    assert r.devices()[0]["approvalStatus"] == "REVOKED"


def test_revoked_coordinator_can_finish_drain_but_cannot_start_workers(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    w, wh = pair(lab, "worker", False)
    enable(lab, d, h)
    enable(lab, w, wh)
    rid = queued(lab, d, workerIds=[w["workerId"]])
    s.dispatch_once()
    assignment = r.runs()[0]
    assert c.patch("/api/v1/platform/devices/" + d["deviceId"], headers=a, json={"approved": False}).status_code == 200
    command = {"assignmentId": assignment["assignmentId"], "epoch": 1, "workerId": w["workerId"], "recoveryIndex": 0}
    assert c.post("/api/v1/device/worker-command", headers=h, json={**command, "action": "start"}).status_code == 401
    process = {"assignmentId": assignment["assignmentId"], "epoch": 1, "workerAlive": False, "coordinatorAlive": False}
    boot(c, wh, "boot-1", processes=[process])
    poll = c.post("/api/v1/device/worker-command", headers=h, json={**command, "action": "poll"})
    assert poll.status_code == 200 and poll.json()["alive"] is False
    report = {
        "sequence": 1,
        "assignmentId": assignment["assignmentId"],
        "epoch": 1,
        "snapshot": {
            "state": {"status": "CANCELLED"},
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": [],
            "artifacts": [],
        },
    }
    boot(c, h, "boot-1", processes=[process], reports=[report])
    s.dispatch_once()
    assert s.get(rid)["status"] == "CANCELLED" and not r.reservations()
    # Drain authority ends with the released assignment.
    assert c.post("/api/v1/device/worker-command", headers=h, json={**command, "action": "poll"}).status_code == 401


def test_reports_deduplicate_and_reject_worker_fabricated_snapshot(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    worker, wh = pair(lab, "second", coordinator=False)
    enable(lab, d, h)
    enable(lab, worker, wh)
    rid = queued(lab, d, workerIds=[d["workerId"], worker["workerId"]])
    s.dispatch_once()
    ar = r.runs()[0]
    report = {
        "sequence": 1,
        "assignmentId": ar["assignmentId"],
        "epoch": ar["epoch"],
        "snapshot": {
            "state": {"status": "RUNNING"},
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": [],
            "artifacts": [],
        },
    }
    boot(c, wh, "boot-1", contribution=True, reports=[report])
    assert r.snapshot(rid)["state"]["status"] == "STARTING"
    boot(c, h, "boot-1", contribution=True, reports=[report])
    boot(
        c,
        h,
        "boot-1",
        contribution=True,
        reports=[{**report, "snapshot": {**report["snapshot"], "state": {"status": "FAILED"}}}],
    )
    assert r.snapshot(rid)["state"]["status"] == "RUNNING"


def test_coordinator_reserved_even_when_not_candidate_worker(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    w, wh = pair(lab, "worker-only", False)
    enable(lab, d, h)
    enable(lab, w, wh)
    rid = queued(lab, d, workerIds=[w["workerId"]])
    s.dispatch_once()
    assert {x["deviceId"] for x in r.reservations()} == {d["deviceId"], w["deviceId"]}


def test_device_owner_cannot_execute_shell_or_impersonate_coordinator(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    assert (
        c.post(
            "/api/v1/device/worker-command", headers=h, json={"kind": "SHELL", "argv": ["touch", "/tmp/forbidden"]}
        ).status_code
        == 422
    )
    enable(lab, d, h)
    rid = queued(lab, d)
    s.dispatch_once()
    ar = r.runs()[0]
    request = {
        "assignmentId": ar["assignmentId"],
        "epoch": ar["epoch"],
        "workerId": "not-selected",
        "action": "start",
        "recoveryIndex": 0,
    }
    assert c.post("/api/v1/device/worker-command", headers=h, json=request).status_code == 403


def test_start_is_durable_before_first_worker_ack(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    w, wh = pair(lab, "worker-only", False)
    enable(lab, d, h)
    enable(lab, w, wh)
    rid = queued(lab, d, workerIds=[w["workerId"]])
    s.dispatch_once()
    ar = r.runs()[0]
    result = c.post(
        "/api/v1/device/worker-command",
        headers=h,
        json={
            "assignmentId": ar["assignmentId"],
            "epoch": ar["epoch"],
            "workerId": w["workerId"],
            "action": "start",
            "recoveryIndex": 0,
        },
    )
    assert result.status_code == 200 and result.json()["alive"] is None
    assert any(cmd["kind"] == "START_WORKER" for cmd in r.commands(w["deviceId"]))


def test_a_restarted_worker_is_a_new_launch_and_never_reads_the_stopped_one(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    w, wh = pair(lab, "worker-only", False)
    enable(lab, d, h)
    enable(lab, w, wh)
    queued(lab, d, workerIds=[w["workerId"]])
    s.dispatch_once()
    ar = r.runs()[0]
    command = {"assignmentId": ar["assignmentId"], "epoch": ar["epoch"], "workerId": w["workerId"], "recoveryIndex": 0}

    def send(action, **extra):
        return c.post("/api/v1/device/worker-command", headers=h, json={**command, "action": action, **extra})

    def starts():
        return [cmd for cmd in r.commands(w["deviceId"]) if cmd["kind"] == "START_WORKER"]

    assert send("start").status_code == 200
    assert "launch" not in starts()[0]  # a first launch keeps the form older agents know
    dead = {"assignmentId": ar["assignmentId"], "epoch": ar["epoch"], "workerAlive": False, "coordinatorAlive": False}
    boot(c, wh, "boot-1", contribution=True, processes=[dead])
    assert send("poll").json()["alive"] is False
    assert send("start", launch=1).status_code == 200
    assert [cmd.get("launch", 0) for cmd in starts()] == [0, 1]  # its own command, not swallowed as a duplicate
    assert send("poll", launch=1).status_code == 503  # the stopped launch 0 is not this one's state
    boot(c, wh, "boot-1", contribution=True, processes=[{**dead, "workerAlive": True, "launch": 1}])
    assert send("poll", launch=1).json()["alive"] is True
    assert send("start", launch=20).status_code == 422


def test_an_app_started_again_during_a_run_may_send_the_same_qualification(lab):
    # c8 run, 2026-10-21: the desktop app sends its qualification at every start; while the run held its GPU the lab
    # refused it, the app stopped its agent and tried again with a new boot, so it never came back into the run
    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    queued(lab, d)
    s.dispatch_once()
    assert r.reservations()
    boot(c, h, "boot-2")  # the whole app was stopped and started again
    with s.db() as db:
        stored = json.loads(db.execute("SELECT self_test FROM devices").fetchone()[0])

    def qualify(profile, boot_id="boot-2"):
        return c.patch("/api/v1/device/qualification", headers=h, json={"bootId": boot_id, "selfTest": profile})

    assert qualify(stored).json() == {"updated": False}
    assert qualify({**stored, "vramTotalMb": stored["vramTotalMb"] + 1}).status_code == 409  # new evidence waits
    assert qualify(stored, "boot-1").status_code == 409  # never from an old boot


def start_command_for(lab, monkeypatch, tmp_path, config):
    """The START_WORKER command the Lab Server queues for a worker, with `config` as the private config."""
    c, s, r, a = lab
    if config is not None:
        (tmp_path / "private").mkdir()
        (tmp_path / "private" / "config.json").write_text(json.dumps(config))
        monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(tmp_path / "private"))
    else:
        monkeypatch.delenv("HETEROES_PRIVATE_CONFIG", raising=False)
    d, h = pair(lab)
    w, wh = pair(lab, "worker-only", False)
    enable(lab, d, h)
    enable(lab, w, wh)
    queued(lab, d, workerIds=[w["workerId"]])
    s.dispatch_once()
    ar = r.runs()[0]
    assert (
        c.post(
            "/api/v1/device/worker-command",
            headers=h,
            json={
                "assignmentId": ar["assignmentId"],
                "epoch": ar["epoch"],
                "workerId": w["workerId"],
                "action": "start",
                "recoveryIndex": 0,
            },
        ).status_code
        == 200
    )
    return next(cmd for cmd in r.commands(w["deviceId"]) if cmd["kind"] == "START_WORKER")


def test_start_worker_carries_the_labs_public_compute_address(lab, monkeypatch, tmp_path):
    command = start_command_for(lab, monkeypatch, tmp_path, {"publicComputeUrl": "https://compute.example.org"})
    assert command["publicComputeUrl"] == "https://compute.example.org"
    assert command["coordinatorUrl"] == "http://100.64.0.1:8769" and command["computeToken"]


@pytest.mark.parametrize(
    "config",
    [
        None,
        {},
        {"publicComputeUrl": None},
        {"publicComputeUrl": "http://compute.example.org"},
        {"publicComputeUrl": "https://192.168.1.2:8081"},
        {"publicComputeUrl": "not a url"},
    ],
)
def test_start_worker_omits_a_missing_or_unusable_public_address(lab, monkeypatch, tmp_path, config):
    assert "publicComputeUrl" not in start_command_for(lab, monkeypatch, tmp_path, config)


def test_the_public_compute_address_is_read_again_each_time(lab, monkeypatch, tmp_path):
    runtime = lab[2]
    (tmp_path / "private").mkdir()
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(tmp_path / "private"))
    for name in ("first", "second"):
        (tmp_path / "private" / "config.json").write_text(
            json.dumps({"publicComputeUrl": f"https://{name}.example.org"})
        )
        assert runtime.public_compute_url() == f"https://{name}.example.org"
    (tmp_path / "private" / "config.json").write_text("{broken")
    assert runtime.public_compute_url() is None


def test_restore_mismatch_quarantine_survives_restart(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    rid = queued(lab, d)
    s.dispatch_once()
    ar = r.runs()[0]
    boot(
        c,
        h,
        "boot-1",
        contribution=True,
        processes=[
            {
                "assignmentId": ar["assignmentId"],
                "epoch": ar["epoch"],
                "workerAlive": False,
                "events": [{"failure": "RESTORE_MISMATCH"}],
            }
        ],
    )
    assert r.devices()[0]["approvalStatus"] == "QUARANTINED"
    assert d["workerId"] in r.capabilities()["quarantinedWorkerIds"]
    again = AgentRuntime()
    again.attach_store(s)
    assert again.devices()[0]["approvalStatus"] == "QUARANTINED"
    assert (
        c.patch(
            "/api/v1/platform/devices/" + d["deviceId"], headers=a, json={"approved": True, "workspaceId": "lab"}
        ).status_code
        == 409
    )


def test_monitoring_events_deduplicate_independently_of_snapshot_sequence(lab):
    import hashlib

    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    rid = queued(lab, d)
    s.dispatch_once()
    ar = r.runs()[0]
    event = {"event": "generation_done", "generation": 0, "t": 100}
    eid = hashlib.sha256(
        (ar["assignmentId"] + json.dumps(event, sort_keys=True, separators=(",", ":"))).encode()
    ).hexdigest()
    envelope = {"eventId": eid, "assignmentId": ar["assignmentId"], "epoch": 1, "event": event}
    for _ in range(2):
        response = boot(c, h, "boot-1", contribution=True, events=[envelope])
        assert response["acceptedEvents"] == [eid]
    with s.db() as db:
        rows = db.execute(
            "SELECT event_id FROM monitoring_events WHERE assignment_id=?", (ar["assignmentId"],)
        ).fetchall()
    assert [row[0] for row in rows] == [eid]


def device_event(assignment, event):
    encoded = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return {
        "eventId": hashlib.sha256((assignment["assignmentId"] + encoded).encode()).hexdigest(),
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "event": event,
    }


def test_a_device_that_cannot_start_the_run_says_why_in_the_event_list(lab):
    c, s, r, a = lab
    (d1, h1), (d2, h2) = pair(lab, "gpu-one"), pair(lab, "gpu-two")
    enable(lab, d1, h1)
    enable(lab, d2, h2)
    first, second = queued(lab, d1, name="First run"), queued(lab, d2, name="Second run")
    s.dispatch_once()
    assignments = {assignment["runId"]: assignment for assignment in r.runs()}
    deferred = {
        "event": "agent_command_deferred",
        "kind": "COORDINATE",
        "attempts": 10,
        "reason": "The coordinator is not reachable on any route yet",
        "t": 200,
    }
    failed = {
        "event": "agent_command_failed",
        "kind": "START_WORKER",
        "attempts": 1,
        "reason": "Invalid run identity",
        "t": 300,
    }
    copied = {"event": "generation_done", "generation": 0, "t": 100}  # the agent also copies the coordinator's events
    other = {
        "event": "agent_command_deferred",
        "kind": "COORDINATE",
        "attempts": 1,
        "reason": "Contribution is OFF for this boot",
        "t": 250,
    }
    boot(
        c,
        h1,
        "boot-1",
        contribution=True,
        events=[device_event(assignments[first], e) for e in (failed, copied, deferred)],
    )
    boot(c, h2, "boot-1", contribution=True, events=[device_event(assignments[second], other)])
    events = c.get("/api/v1/events", headers=a).json()

    def of(run_id):
        return [(e["eventType"], e["severity"], e["message"]) for e in events if e["experimentId"] == run_id]

    assert of(first) == [
        ("agent_command_deferred", "WARNING", "The coordinator is not reachable on any route yet"),
        ("agent_command_failed", "ERROR", "Invalid run identity"),
    ]
    assert of(second) == [("agent_command_deferred", "WARNING", "Contribution is OFF for this boot")]
    assert len({e["eventId"] for e in events}) == 3


def test_event_severity_follows_the_event_name_and_a_missing_reason_falls_back_to_it(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    rid = queued(lab, d)
    s.dispatch_once()
    assignment = r.runs()[0]
    snapshot = {
        "state": {"status": "RUNNING"},
        "generations": [],
        "candidates": [],
        "attempts": [],
        "artifacts": [],
        "events": [
            {"event": "generation_failed", "t": 50},
            {"event": "managed_error", "error": "boom", "t": 55},
            {"event": "worker_unavailable", "t": 60},
            {"event": "worker_start_unknown", "t": 65},
        ],
    }
    report = {
        "sequence": 1,
        "assignmentId": assignment["assignmentId"],
        "epoch": assignment["epoch"],
        "snapshot": snapshot,
    }
    bare = {"event": "agent_command_deferred", "kind": "COORDINATE", "attempts": 1, "t": 70}
    boot(c, h, "boot-1", contribution=True, reports=[report], events=[device_event(assignment, bare)])
    s.dispatch_once()
    events = c.get("/api/v1/events", headers=a).json()
    assert [(e["eventType"], e["severity"], e["message"]) for e in events] == [
        ("generation_failed", "ERROR", "generation failed"),
        ("managed_error", "ERROR", "boom"),
        ("worker_unavailable", "WARNING", "worker unavailable"),
        ("worker_start_unknown", "WARNING", "worker start unknown"),
        ("agent_command_deferred", "WARNING", "agent command deferred"),
    ]
    # the ids that the Events page links to: coordinator events by position, device events by arrival
    assert [e["eventId"] for e in events[:4]] == [f"{rid}.e{n}" for n in (0, 1, 2, 3)]
    assert events[4]["eventId"].startswith(f"{rid}.m")


def test_backup_policy_change_does_not_mutate_frozen_assignment(lab):
    c, s, r, a = lab
    d, h = pair(lab)
    enable(lab, d, h)
    rid = queued(lab, d)
    s.dispatch_once()
    original = s.get(rid)
    hash_before = original["configHash"]
    result = c.patch("/api/v1/experiments/" + rid + "/backup-policy", headers=a, json={"interval": 2, "retain": 5})
    assert result.status_code == 200 and result.json()["appliesBeforeNextGeneration"]
    assert s.get(rid)["configHash"] == hash_before
    assert s.get(rid)["backupPolicy"] == {"interval": 1, "retain": 3}
    assert s.get(rid)["requestedBackupPolicy"] == {"interval": 2, "retain": 5}
    s.dispatch_once()
    assert len(r.runs()) == 1
    assert any(cmd["kind"] == "UPDATE_BACKUP_POLICY" for cmd in r.commands(d["deviceId"]))


# r11 ships the desktop-v3 reference; the r10 desktop-v1 Windows reference lives on as its regression artifact.
LEGACY_WINDOWS_REFERENCE = (
    Path(__file__).parents[2] / "runtime/artifacts/regression/2026-10-10-m3-native-profile/reference.json"
)


def test_native_windows_admission_requires_exact_reference_and_worker_only():
    from backend.devices import SelfTest
    from pydantic import ValidationError
    import pathlib

    reference = json.loads(LEGACY_WINDOWS_REFERENCE.read_text())
    proof = {k: reference[k] for k in ("recipeHash", "parentSha256", "perturbedSha256", "restoredSha256", "reward")}
    proof.update(
        passed=True,
        repeatIdentical=True,
        predictionProbePassed=True,
        probeOutputsSha256=reference["predictionProbe"]["outputsSha256"],
    )
    data = {
        "passed": True,
        "coordinator": False,
        "gpuName": "CPU test fixture",
        "vramTotalMb": 12000,
        "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
        "platform": "windows",
        "runtimeProfile": "desktop-v1",
        "compatibility": proof,
    }
    assert not SelfTest(**data).coordinator
    for changes in (
        {"coordinator": True},
        {"runtimeProfile": "legacy"},
        {"passed": False},
        {"compatibility": {**proof, "repeatIdentical": False}},
        {"compatibility": {**proof, "reward": 0.25}},
        {"compatibility": {**proof, "predictionProbePassed": False}},
        {"compatibility": {**proof, "probeOutputsSha256": "e" * 64}},
        {"compatibility": {**proof, "recipeHash": "e" * 64}},
        {"compatibility": {**proof, "restoredSha256": "f" * 64}},
    ):
        with pytest.raises(ValidationError):
            SelfTest(**{**data, **changes})


def test_native_windows_v3_worker_admission_is_bound_to_the_shipped_reference():
    import copy
    import pathlib

    from backend.devices import SelfTest
    from backend.policies import v3_qualification
    from pydantic import ValidationError

    evidence = pathlib.Path(__file__).parents[2] / "docs/evidence/2026-10-19-v3-qualification-reference"
    data = json.loads((evidence / "windows-3060-first.json").read_text())["result"]  # the real RTX 3060 result
    admitted = SelfTest(**data)
    assert (admitted.platform, admitted.coordinator, admitted.recipeVersions) == ("windows", False, [3])
    model = data["qualifiedModelHashes"][0]
    assert v3_qualification(admitted.model_dump(), model) is None
    assert v3_qualification({**admitted.model_dump(), "qualifiedModelHashes": []}, model) == "model"

    def changed(path, value):
        body = copy.deepcopy(data)
        *parents, key = path
        target = body
        for name in parents:
            target = target[name]
        target[key] = value
        return body

    for path, value in [
        (("runtimeProfile",), "desktop-v1"),
        (("recipeVersions",), [1, 3]),
        (("recipeVersions",), [1]),  # a v3 profile never stands in for the v1 Windows evidence
        (("qualifiedModelHashes",), ["e" * 64]),
        (("qualifiedModelHashes",), [data["qualifiedModelHashes"][0], "e" * 64]),
        (("compatibility", "recipeV3Lora", "modelManifestHash"), "e" * 64),
        (("compatibility", "recipeV3Lora", "passed"), False),
        (("compatibility", "recipeV3Lora"), {}),
        (("compatibility", "recipeV3Lora", "outputsHash"), "e" * 64),
        (("compatibility", "recipeV3Lora", "restoredSha256"), "e" * 64),
        (("compatibility", "recipeV3Lora", "repeatIdentical"), False),
        (("compatibility", "recipeV3", "negativeProbeHash"), "e" * 64),
        (("compatibility", "recipeV3", "recipeHash"), "e" * 64),
        (("compatibility", "initialAdapterSha256"), "e" * 64),
        (("compatibility", "peftVersion"), "0.21.1"),
        (("compatibility", "repeatIdentical"), False),
    ]:
        with pytest.raises(ValidationError):
            SelfTest(**changed(path, value))


def test_turning_a_device_off_drains_running_jobs_and_preserves_its_queue(setup):
    client, store, runtime = setup
    admin = login(client, "admin")
    ids = [draft(client, admin, name=f"GPU job {i}").json()["experimentId"] for i in range(2)]
    for rid in ids:
        client.post(f"/api/v1/experiments/{rid}/submit", headers=admin)
    store.dispatch_once()
    assert submitted(runtime) == ids[:1]
    device = next(d for d in runtime.devices() if d["workerId"] == "5070ti")
    off = client.post(
        f"/api/v1/devices/{device['deviceId']}/contribution", json={"enabled": False, "bootId": "boot-1"}, headers=admin
    )
    assert off.status_code == 200
    assert store.get(ids[0])["cancelRequested"]
    assert store.get(ids[1])["status"] == "QUEUED" and not store.get(ids[1])["cancelRequested"]
    assert [(did, c["assignmentId"]) for did, c in pending_commands(runtime, "CANCEL_ASSIGNMENT")] == [
        (device["deviceId"], runtime.runs()[0]["assignmentId"])
    ]


def test_an_offline_queue_waits_then_dispatches_when_contribution_returns(lab):
    client, store, runtime, admin = lab
    device, auth = pair(lab)
    enable(lab, device, auth)
    rid = queued(lab, device)
    off = client.post(
        f"/api/v1/devices/{device['deviceId']}/contribution",
        json={"enabled": False, "bootId": "boot-1"},
        headers=admin,
    )
    assert off.status_code == 200
    store.dispatch_once()
    assert store.get(rid)["status"] == "QUEUED" and not store.get(rid)["cancelRequested"]
    assert not runtime.runs() and not runtime.reservations()
    enable(lab, device, auth)
    store.dispatch_once()
    assert store.get(rid)["status"] == "STARTING"


def test_resource_revocation_still_cancels_queued_jobs_and_explicit_cancel_still_works(lab):
    client, store, _, admin = lab
    device, auth = pair(lab)
    first, second = queued(lab, device), queued(lab, device, name="Second queued job")
    assert client.post(f"/api/v1/experiments/{first}/cancel", headers=admin).status_code == 200
    assert store.get(first)["status"] == "CANCELLED"
    result = client.patch(f"/api/v1/platform/devices/{device['deviceId']}", json={"approved": False}, headers=admin)
    assert result.status_code == 200
    assert store.get(second)["status"] == "CANCELLED"
