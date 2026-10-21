import json

import pytest
from heteroes.product.agent import Agent, InvalidCommand
from heteroes.product.files import write_json, read_json


def agent(tmp_path):
    write_json(
        tmp_path / "config.json",
        {
            "serverUrl": "http://127.0.0.1:8002",
            "deviceId": "a" * 32,
            "workerId": "test",
            "deviceToken": "private",
            "stateDirectory": str(tmp_path / "state"),
            "modelPath": "/model",
            "computeUrl": "http://127.0.0.1:8769",
            "workerHost": "127.0.0.1",
            "workerPort": 8769,
        },
    )
    return Agent(tmp_path / "config.json")


def test_boot_resets_off_and_stale_enable_is_rejected(tmp_path):
    a = agent(tmp_path)
    a.handle({"commandId": "1", "kind": "SET_CONTRIBUTION", "bootId": a.boot_id, "enabled": True})
    assert a.enabled
    a.handle({"commandId": "2", "kind": "SET_CONTRIBUTION", "bootId": "old", "enabled": True})
    b = Agent(tmp_path / "config.json")
    assert not b.enabled and b.boot_id != a.boot_id


def test_shell_commands_and_bad_paths_never_execute(tmp_path):
    a = agent(tmp_path)
    for cmd in (
        {"commandId": "x", "kind": "SHELL", "argv": ["touch", "/tmp/unsafe"]},
        {"commandId": "x", "kind": "START_WORKER", "runId": "../escape", "assignmentId": "a" * 32, "epoch": 1},
    ):
        with pytest.raises(ValueError):
            a.handle(cmd)


def test_coordinator_recovery_requires_explicit_on(tmp_path, monkeypatch):
    a = agent(tmp_path)
    root = a.manager.root / ("b" * 32)
    root.mkdir()
    write_json(root / "config.json", {"runId": "b" * 32})
    write_json(root / "state.json", {"status": "RECOVERING"})
    launched = []
    monkeypatch.setattr(a.manager, "_launch", lambda r: launched.append(r))
    a.manager.launch(root)
    assert launched == []
    a.enabled = True
    a.manager.launch(root)
    assert launched == [root]


def test_cancel_before_start_fences_delayed_worker_command(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    cancel = {"commandId": "cancel", "kind": "CANCEL_ASSIGNMENT", "assignmentId": "b" * 32, "epoch": 1}
    a.handle(cancel)
    started = []
    monkeypatch.setattr(a, "_worker", lambda *args: started.append(args))
    a.handle(
        {"commandId": "late-start", "kind": "START_WORKER", "assignmentId": "b" * 32, "epoch": 1, "runId": "c" * 32}
    )
    assert started == []
    assert a.observe()[0]["workerAlive"] is False


def test_unknown_pid_birth_is_not_confirmed_dead():
    from heteroes.product.agent import owned_state

    assert owned_state({"pid": 123, "birth": None}) is None
    assert owned_state(None, intent=True) is None


def test_duplicate_agent_does_not_change_current_boot(tmp_path):
    a = agent(tmp_path)
    a = Agent(tmp_path / "config.json", lock=True)
    before = read_json(a.root / "boot.json")
    with pytest.raises(BlockingIOError):
        Agent(tmp_path / "config.json", lock=True)
    assert read_json(a.root / "boot.json") == before
    a.instance_lock.close()


def test_monitoring_ack_is_durable_and_not_requeued(tmp_path, monkeypatch):
    a = agent(tmp_path)
    root = a.manager.root / ("b" * 32)
    root.mkdir()
    write_json(root / "assignment.json", {"assignmentId": "c" * 32, "epoch": 1})
    event = {"event": "generation_done", "generation": 0, "t": 1}
    snap = {
        "state": {"status": "COMPLETED"},
        "events": [event],
        "artifacts": [],
        "generations": [],
        "candidates": [],
        "attempts": [],
    }
    monkeypatch.setattr(a.manager, "snapshot", lambda _: dict(snap))

    def reply(_, body):
        return {
            "approvalStatus": "APPROVED",
            "desiredContribution": False,
            "commands": [],
            "acceptedReports": [{"assignmentId": "c" * 32, "sequence": body["reports"][0]["sequence"]}],
            "acceptedEvents": [e["eventId"] for e in body["events"]],
        }

    monkeypatch.setattr(a, "call", reply)
    a.cycle()
    a.observe()
    with a.db() as db:
        assert db.execute("SELECT count(*) FROM event_outbox WHERE ack=0").fetchone()[0] == 0


def test_large_monitoring_projection_preserves_completion_and_latest_metrics():
    import json
    from heteroes.product.agent import bounded_snapshot

    generations = [
        {"generationId": str(i), "status": "COMPLETED", "committedCandidateCount": 256, "modelVersion": "hash"}
        for i in range(1000)
    ]
    snapshot = {
        "state": {"status": "COMPLETED", "finalWeightsSha256": "final-hash"},
        "generations": generations,
        "events": [{"data": "x" * 10000} for _ in range(1000)],
        "candidates": [{"data": "y" * 1000} for _ in range(2000)],
        "attempts": [{"data": "z" * 1000} for _ in range(6000)],
        "artifactContents": {},
    }
    result = bounded_snapshot(snapshot)
    assert len(json.dumps(result).encode()) <= 1_250_000
    assert result["completedGenerationCount"] == 1000
    assert result["latestGeneration"] == generations[-1]
    assert result["state"] == {"status": "COMPLETED", "finalWeightsSha256": "final-hash"}
    assert result["monitoringPartial"]


def test_worker_only_observation_does_not_invent_unknown_coordinator(tmp_path, monkeypatch):
    a = agent(tmp_path)
    command = {"assignmentId": "b" * 32, "epoch": 1, "recoveryIndex": 0}
    directory = a.worker_directory(command)
    write_json(directory / "assignment.json", command)
    monkeypatch.setattr(a, "_worker", lambda *_: {"alive": False, "ready": False, "events": []})
    state = a.observe()[0]
    assert state["coordinatorAlive"] is False and state["workerAlive"] is False


def test_desktop_profile_cannot_coordinate(tmp_path):
    a = agent(tmp_path)
    a.config["workerOnly"] = True
    a.enabled = True
    with pytest.raises(ValueError, match="worker-only"):
        a.handle({"commandId": "coordinate", "kind": "COORDINATE"})


def test_desktop_quit_fences_late_enable_for_current_boot(tmp_path):
    a = agent(tmp_path)
    a.shutdown_requested = True
    with pytest.raises(RuntimeError, match="shutdown"):
        a.handle({"commandId": "late-enable", "kind": "SET_CONTRIBUTION", "bootId": a.boot_id, "enabled": True})
    assert not a.enabled


def test_released_assignment_never_launches_a_delayed_worker(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    with a.db() as db:
        db.execute("INSERT INTO released VALUES (?)", ("b" * 32,))
    launched = []
    monkeypatch.setattr(a, "_worker", lambda *args: launched.append(args))
    a.handle({"commandId": "old-start", "kind": "START_WORKER", "assignmentId": "b" * 32, "epoch": 1})
    assert launched == []
    with a.db() as db:
        assert db.execute('SELECT 1 FROM processed WHERE id="old-start"').fetchone()


def test_resume_validates_checkpoint_preserves_ledger_and_rejects_old_epoch(tmp_path):
    import hashlib
    import sqlite3
    from heteroes.product.recovery import capture_point

    a = agent(tmp_path)
    a.enabled = True
    cfg = {
        "runId": "b" * 32,
        "workerIds": ["test"],
        "workload": "arith16",
        "decodeEngine": "hf_generate",
        "maxGenerations": 3,
        "candidatesPerGeneration": 4,
        "alpha": 0.001,
        "sigma": 0.001,
        "schedulerPolicy": "greedy",
        "syncMode": "synchronous",
        "backupPolicy": {"interval": 1, "retain": 3},
    }
    old = {"assignmentId": "c" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "old-private"}}
    a.manager.accept(old)
    root = a.manager.directory(cfg["runId"])
    (root / "weights").mkdir()
    payload = b"toy pause weights"
    sha = hashlib.sha256(payload).hexdigest()
    (root / "weights" / f"{sha}.bin").write_bytes(payload)
    with sqlite3.connect(root / "ledger.sqlite") as db:
        db.execute(
            "CREATE TABLE generation_update(generation INTEGER,child_weights_sha256 TEXT,parent_weights_sha256 TEXT,applied_at REAL)"
        )
        db.execute("INSERT INTO generation_update VALUES (0,?,?,1)", (sha, sha))
    summary = {"generation": 0, "child_sha256": sha, "parent_sha256": sha}
    point = capture_point(root, summary, {}, cfg["backupPolicy"], final=True)
    paused = {
        "pointId": point.name,
        "generation": 0,
        "childWeightsSha256": sha,
        "parentWeightsSha256": sha,
        "verified": True,
    }
    write_json(root / "pause-point.json", paused)
    (root / "pause.flag").touch()
    a.manager.save(root, status="PAUSED", workerStates={"test": {"alive": False, "confirmed": True}})
    ledger_before = (root / "ledger.sqlite").read_bytes()
    resumed = {
        **old,
        "assignmentId": "d" * 32,
        "epoch": 2,
        "resumeFrom": paused,
        "computeGrants": {"test": "new-private"},
    }
    # Corrupt the independently retained checkpoint, then retry after restoring
    # it. A failed preflight leaves the old paused epoch intact.
    file = point / "weights" / f"{sha}.bin"
    file.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        a.manager.accept(resumed)
    assert a.manager.state(root)["status"] == "PAUSED"
    file.write_bytes(payload)
    a.manager.accept(resumed)
    assert a.manager.state(root)["status"] == "STARTING"
    assert not (root / "pause.flag").exists()
    assert read_json(root / "assignment.json")["epoch"] == 2
    assert read_json(root / "device-grants.json") == {"test": "new-private"}
    assert (root / "ledger.sqlite").read_bytes() == ledger_before
    with pytest.raises(ValueError, match="epoch"):
        a.manager.accept(old)


def test_detail_capability_negotiates_before_sending_extended_observations(tmp_path, monkeypatch):
    a = agent(tmp_path)
    sent = []
    monkeypatch.setattr(a, "observe", lambda: [])
    row = {
        "sampledAt": 1,
        "sessionStartedAt": 1,
        "source": "host-observation",
        "disks": [],
        "host": {"platform": "linux", "cores": [{"id": "cpu0"}]},
        "power": {"hostId": "local"},
    }
    monkeypatch.setattr(a.telemetry, "sample", lambda: row)

    def reply(path, body):
        sent.append(body)
        return {
            "approvalStatus": "APPROVED",
            "desiredContribution": False,
            "commands": [],
            "acceptedReports": [],
            "acceptedEvents": [],
            "telemetrySupported": True,
            "detailedTelemetrySupported": len(sent) >= 2,
        }

    monkeypatch.setattr(a, "call", reply)
    a.cycle()
    a.cycle()
    a.cycle()
    assert "telemetry" not in sent[0]
    assert "power" not in sent[1]["telemetry"] and "cores" not in sent[1]["telemetry"]["host"]
    assert sent[2]["telemetry"]["power"] == {"hostId": "local"}
    assert not a.enabled


def poll_with(a, monkeypatch, commands):
    """Make the agent's next polls return `commands`; the list of request bodies is returned."""
    sent = []
    monkeypatch.setattr(a, "observe", lambda: [])

    def reply(path, body):
        sent.append(body)
        return {
            "approvalStatus": "APPROVED",
            "desiredContribution": False,
            "commands": commands,
            "acceptedReports": [],
            "acceptedEvents": [],
            "telemetrySupported": False,
            "detailedTelemetrySupported": False,
        }

    monkeypatch.setattr(a, "call", reply)
    return sent


def test_unknown_command_kind_is_acknowledged_and_does_not_block_a_following_cancel(tmp_path, monkeypatch):
    a = agent(tmp_path)
    cancel = {"commandId": "cancel", "kind": "CANCEL_ASSIGNMENT", "assignmentId": "b" * 32, "epoch": 1}
    sent = poll_with(a, monkeypatch, [{"commandId": "future", "kind": "KIND_FROM_A_NEWER_SERVER"}, cancel])
    a.cycle()
    a.cycle()
    assert (a.root / "cancelled-assignments" / ("b" * 32 + ".json")).exists()
    assert {"future", "cancel"} <= set(sent[1]["acknowledgements"])


def test_malformed_identities_are_acknowledged_not_retried_forever(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    bad = {"commandId": "bad", "kind": "START_WORKER", "runId": "../escape", "assignmentId": "a" * 32, "epoch": 1}
    sent = poll_with(a, monkeypatch, [bad])
    a.cycle()
    a.cycle()
    assert "bad" in sent[1]["acknowledgements"]


def test_state_dependent_failure_is_retried_but_later_commands_still_run(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True

    def broken(command, action):
        raise OSError("disk full")

    monkeypatch.setattr(a, "_worker", broken)
    start = {"commandId": "start", "kind": "START_WORKER", "assignmentId": "c" * 32, "epoch": 1, "runId": "d" * 32}
    cancel = {"commandId": "cancel", "kind": "CANCEL_ASSIGNMENT", "assignmentId": "b" * 32, "epoch": 1}
    sent = poll_with(a, monkeypatch, [start, cancel])
    a.cycle()
    a.cycle()
    assert (a.root / "cancelled-assignments" / ("b" * 32 + ".json")).exists()
    assert "cancel" in sent[1]["acknowledgements"] and "start" not in sent[1]["acknowledgements"]
    with a.db() as db:
        assert db.execute('SELECT attempts FROM command_failures WHERE id="start"').fetchone()[0] == 2


def test_failed_safety_command_is_never_acknowledged(tmp_path, monkeypatch):
    a = agent(tmp_path)
    cancel = {"commandId": "cancel", "kind": "CANCEL_ASSIGNMENT", "assignmentId": "b" * 32, "epoch": 1}
    write_json(a.manager.root / ("e" * 32) / "assignment.json", {"assignmentId": "b" * 32, "epoch": 1})

    def broken(run_id):
        raise OSError("read-only file system")

    monkeypatch.setattr(a.manager, "cancel", broken)
    sent = poll_with(a, monkeypatch, [cancel])
    a.cycle()
    a.cycle()
    assert "cancel" not in sent[1]["acknowledgements"]


def test_reporting_a_failure_cannot_itself_break_the_cycle(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    # SQLite would store a text epoch; the server rejects an event whose epoch is not an
    # integer, and with it every later poll of this device.
    odd = {"commandId": "odd", "kind": "START_WORKER", "assignmentId": "c" * 32, "epoch": "abc", "runId": "d" * 32}
    sent = poll_with(a, monkeypatch, [odd])
    a.cycle()
    a.cycle()
    assert "odd" in sent[1]["acknowledgements"]
    with a.db() as db:
        assert db.execute("SELECT count(*) FROM event_outbox").fetchone()[0] == 0


def test_deferred_command_is_waiting_not_failing(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.shutdown_requested = True
    enable = {"commandId": "late", "kind": "SET_CONTRIBUTION", "bootId": a.boot_id, "enabled": True}
    sent = poll_with(a, monkeypatch, [enable])
    a.cycle()
    a.cycle()
    assert "late" not in sent[1]["acknowledgements"]
    with a.db() as db:
        assert db.execute("SELECT count(*) FROM command_failures").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM event_outbox").fetchone()[0] == 0


def test_command_failure_reaches_the_server_as_a_throttled_assignment_event(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True

    def broken(command, action):
        raise OSError("disk full")

    monkeypatch.setattr(a, "_worker", broken)
    start = {"commandId": "start", "kind": "START_WORKER", "assignmentId": "c" * 32, "epoch": 3, "runId": "d" * 32}
    poll_with(a, monkeypatch, [start])
    for _ in range(3):
        a.cycle()
    with a.db() as db:
        rows = db.execute("SELECT assignment_id,epoch,body FROM event_outbox").fetchall()
    assert len(rows) == 1 and rows[0][:2] == ("c" * 32, 3)
    event = __import__("json").loads(rows[0][2])
    assert event["event"] == "agent_command_failed" and event["errorType"] == "OSError" and event["attempts"] == 1


def outbox_events(a):
    with a.db() as db:
        return [json.loads(body) for (body,) in db.execute("SELECT body FROM event_outbox ORDER BY rowid")]


def coordinate(**extra):
    return {
        "commandId": "coord",
        "kind": "COORDINATE",
        "assignmentId": "c" * 32,
        "epoch": 3,
        "runId": "d" * 32,
        **extra,
    }


def test_deferred_command_tells_the_server_why_at_attempts_1_and_10(tmp_path, monkeypatch):
    a = agent(tmp_path)  # contribution is OFF for this boot, so the coordinator command has to wait
    sent = poll_with(a, monkeypatch, [coordinate()])
    for _ in range(9):
        a.cycle()
    [event] = outbox_events(a)
    assert event["event"] == "agent_command_deferred" and event["attempts"] == 1
    assert (event["commandId"], event["kind"]) == ("coord", "COORDINATE")
    assert event["reason"] == "Contribution is OFF for this boot"
    a.cycle()
    assert [e["attempts"] for e in outbox_events(a)] == [1, 10]
    assert not any("coord" in body["acknowledgements"] for body in sent)
    with a.db() as db:
        assert db.execute('SELECT attempts FROM command_deferrals WHERE id="coord"').fetchone()[0] == 10
        assert db.execute("SELECT count(*) FROM command_failures").fetchone()[0] == 0


def test_deferral_is_reported_at_attempts_100_and_1000_and_not_in_between(tmp_path):
    a = agent(tmp_path)
    for attempt, reported in ((99, False), (100, True), (101, False), (1000, True), (1001, False)):
        before = len(outbox_events(a))
        with a.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO command_deferrals VALUES (?,?,?,?,0)",
                ("coord", "COORDINATE", "RuntimeError", attempt - 1),
            )
        a.run_commands([coordinate()])
        assert len(outbox_events(a)) - before == reported, attempt


@pytest.mark.parametrize("report,error", [("record_failure", InvalidCommand), ("record_deferral", RuntimeError)])
@pytest.mark.parametrize(
    "identity", [{"assignmentId": "not-hex"}, {"assignmentId": None}, {"epoch": 0}, {"epoch": "3"}]
)
def test_nothing_is_queued_for_a_command_without_a_valid_assignment_identity(tmp_path, report, error, identity):
    a = agent(tmp_path)
    getattr(a, report)(coordinate(**identity), error("x"))
    assert outbox_events(a) == []


def test_deferral_count_survives_an_agent_restart(tmp_path):
    a = agent(tmp_path)
    for _ in range(9):
        a.run_commands([coordinate()])
    b = Agent(tmp_path / "config.json")
    b.run_commands([coordinate()])
    assert [e["attempts"] for e in outbox_events(b)] == [1, 10]


def test_failure_event_gives_a_reason_only_for_the_agents_own_errors(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    bad = {"commandId": "bad", "kind": "START_WORKER", "assignmentId": "c" * 32, "epoch": 1, "runId": "../escape"}

    def broken(command, action):
        raise OSError("disk full: /home/someone/private/path")

    monkeypatch.setattr(a, "_worker", broken)
    start = {"commandId": "start", "kind": "START_WORKER", "assignmentId": "c" * 32, "epoch": 1, "runId": "d" * 32}
    a.config["workerOnly"] = True
    worker_only = coordinate(commandId="worker-only")
    a.run_commands([bad, start, worker_only])
    own, library, plain = outbox_events(a)
    assert own["event"] == library["event"] == plain["event"] == "agent_command_failed"
    assert own["reason"] == "Invalid run identity"
    assert library["errorType"] == "OSError" and "reason" not in library
    assert plain["errorType"] == "ValueError" and plain["reason"] == "This device profile is worker-only"


@pytest.mark.parametrize(
    "report,error",
    [("record_failure", InvalidCommand), ("record_deferral", RuntimeError)],
)
def test_reason_hides_urls_and_is_cut_to_200_characters(tmp_path, report, error):
    a = agent(tmp_path)
    getattr(a, report)(
        coordinate(), error("see https://grant.example/v1?token=abc123 and ftp://files.example/x " + "y" * 300)
    )
    [event] = outbox_events(a)
    assert "abc123" not in event["reason"] and "grant.example" not in event["reason"]
    assert event["reason"].startswith("see <url> and <url> y") and len(event["reason"]) == 200


PRIVATE = "http://100.64.0.1:8765"
PUBLIC = "https://compute.example.org"


def start_command(**extra):
    return {
        "commandId": "start",
        "kind": "START_WORKER",
        "assignmentId": "c" * 32,
        "epoch": 1,
        "runId": "d" * 32,
        "workerId": "test",
        "recoveryIndex": 0,
        "coordinatorUrl": PRIVATE,
        "bulkUrl": PRIVATE,
        "computeToken": "grant",
        **extra,
    }


def test_the_private_route_is_used_when_it_answers(tmp_path, monkeypatch):
    a = agent(tmp_path)
    monkeypatch.setattr("heteroes.product.agent.reachable", lambda url, token: url == PRIVATE)
    route = a.choose_route(start_command(publicComputeUrl=PUBLIC))
    assert route == {"coordinatorUrl": PRIVATE, "bulkUrl": PRIVATE, "replayOnly": False}


def test_without_the_private_route_a_worker_uses_the_public_one_for_replay_only(tmp_path, monkeypatch):
    a = agent(tmp_path)
    probed = []
    monkeypatch.setattr(
        "heteroes.product.agent.reachable", lambda url, token: probed.append((url, token)) or url == PUBLIC
    )
    route = a.choose_route(start_command(publicComputeUrl=PUBLIC))
    assert route == {"coordinatorUrl": PUBLIC, "bulkUrl": None, "replayOnly": True}
    assert probed == [(PRIVATE, "grant"), (PUBLIC, "grant")]


def test_a_worker_that_reaches_neither_route_waits_instead_of_failing(tmp_path, monkeypatch):
    a = agent(tmp_path)
    monkeypatch.setattr("heteroes.product.agent.reachable", lambda url, token: False)
    with pytest.raises(RuntimeError, match="coordinator"):
        a.choose_route(start_command(publicComputeUrl=PUBLIC))


def test_without_a_public_address_the_command_is_used_as_it_always_was(tmp_path, monkeypatch):
    a = agent(tmp_path)
    monkeypatch.setattr("heteroes.product.agent.reachable", lambda *args: pytest.fail("no probe is needed"))
    assert a.choose_route(start_command()) == {"coordinatorUrl": PRIVATE, "bulkUrl": PRIVATE, "replayOnly": False}


def launch_arguments(a, monkeypatch, command):
    captured = []
    monkeypatch.setattr(
        "heteroes.product.agent.remote_handle",
        lambda request: captured.append(request) or {"alive": True, "ready": False, "events": []},
    )
    a.enabled = True
    a.handle(command)
    return captured[0]["argv"]


def test_a_replay_only_worker_is_started_without_bulk_and_with_a_longer_chain(tmp_path, monkeypatch):
    a = agent(tmp_path)
    monkeypatch.setattr("heteroes.product.agent.reachable", lambda url, token: url == PUBLIC)
    argv = launch_arguments(a, monkeypatch, start_command(publicComputeUrl=PUBLIC))
    assert argv[argv.index("--coordinator-url") + 1] == PUBLIC
    assert "--no-bulk" in argv and "--bulk-url" not in argv
    assert argv[argv.index("--replay-max-chain") + 1] == "64"


def test_a_worker_on_the_private_route_keeps_its_bulk_and_the_default_chain(tmp_path, monkeypatch):
    a = agent(tmp_path)
    monkeypatch.setattr("heteroes.product.agent.reachable", lambda url, token: True)
    argv = launch_arguments(a, monkeypatch, start_command(publicComputeUrl=PUBLIC))
    assert argv[argv.index("--bulk-url") + 1] == PRIVATE
    assert "--no-bulk" not in argv and "--replay-max-chain" not in argv


def test_reachable_accepts_only_a_coordinator_that_says_it_is_up(tmp_path):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from heteroes.product.agent import reachable

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            token = self.headers.get("Authorization")
            good = token == "Bearer grant" and self.path == "/v1/health"
            if token == "Bearer portal":  # a captive portal: 200 and an HTML page
                body, status = b"<html>please sign in</html>", 200
            elif token == "Bearer down":  # a server that answers 200 but says it is not up
                body, status = json.dumps({"ok": False}).encode(), 200
            else:
                body, status = (
                    json.dumps({"ok": True, "status": "up"} if good else {"ok": False}).encode(),
                    200 if good else 401,
                )
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        assert reachable(url, "grant") is True
        assert reachable(url, "wrong") is False
        assert reachable(url, "portal") is False and reachable(url, "down") is False
    finally:
        server.shutdown()
        server.server_close()
    assert reachable(url, "grant") is False  # nothing listens any more


def test_agent_requests_carry_the_heteroes_user_agent(tmp_path):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from heteroes.http_transport import USER_AGENT
    from heteroes.product.agent import reachable, request

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.answer()

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.answer()

        def answer(self):
            seen.append(self.headers.get("User-Agent"))
            body = json.dumps({"ok": True, "status": "up"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        request(url, "/api/v1/device/poll", "token", {"a": 1})
        assert reachable(url, "grant") is True
    finally:
        server.shutdown()
        server.server_close()
    assert seen == [USER_AGENT, USER_AGENT]


def test_v3_worker_receives_the_frozen_config_and_transferred_inputs(tmp_path, monkeypatch):
    a = agent(tmp_path)
    cfg = {"recipeVersion": 3, "scorer": {"kind": "declarative"}}
    prepared = {
        "modelPath": "/local/model",
        "datasetPath": "/local/data.json",
        "modelManifestPath": "/local/manifest.json",
    }
    calls = []
    monkeypatch.setattr("heteroes.study.prepare.prepare", lambda *args: calls.append(args) or prepared)
    argv = launch_arguments(a, monkeypatch, start_command(studyConfig=cfg))
    assert calls[0][2] == cfg
    assert argv[argv.index("--dataset") + 1] == prepared["datasetPath"]
    assert argv[argv.index("--model-path") + 1] == prepared["modelPath"]
    from pathlib import Path

    path = Path(argv[argv.index("--run-config") + 1])
    assert read_json(path) == cfg
    # a v3 recipe may fix its chunk: the worker must not be told another one
    assert "--chunk" not in argv


def test_a_v1_worker_keeps_the_fp32_chunk(tmp_path, monkeypatch):
    argv = launch_arguments(agent(tmp_path), monkeypatch, start_command())
    assert argv[argv.index("--chunk") + 1] == "16"


def _v3_config(run_id):
    return {
        "runId": run_id,
        "workerIds": ["test"],
        "workload": "text_v3",
        "candidatesPerGeneration": 4,
        "maxGenerations": 2,
        "alpha": 0.0005,
        "sigma": 0.001,
        "decodeEngine": "hf_generate",
        "schedulerPolicy": "greedy",
        "syncMode": "synchronous",
        "backupPolicy": {"interval": 1, "retain": 3},
        "recipeVersion": 3,
        "modelManifest": {"modelId": "m", "revision": "r", "files": {}},
        "modelSource": "REFERENCE",
        "datasetObjectSha256": "d" * 64,
        "datasetIdentity": {"contentHash": "e" * 64, "splitHashes": {}},
        "batchSize": 4,
        "batchSeed": 11,
        "sigmaSchedule": "constant",
        "sigmaMinimum": 0.001,
        "maxNewTokens": 16,
        "validationInterval": 1,
        "weightSpace": {"kind": "full"},
        "antithetic": False,
        "scorer": {
            "kind": "declarative",
            "name": "exact-string",
            "version": 1,
            "codeSha256": None,
            "config": {"answerField": "answer", "strip": True, "casefold": True},
        },
        "coefficientRule": "zscore@1",
        "systemPrompt": None,
    }


def test_a_study_coordinator_never_launches_before_its_inputs_are_prepared(tmp_path, monkeypatch):
    # Found on the packaged r11 candidate2 (2026-10-20): the supervisor thread launched the coordinator while accept()
    # was still transferring the dataset, and the coordinator died with KeyError: 'datasetPath'.
    a = agent(tmp_path)
    a.enabled = True
    cfg = _v3_config("f" * 32)
    launched = []
    monkeypatch.setattr(a.manager, "launch", lambda root: launched.append(root))
    root = a.manager.directory(cfg["runId"])

    def slow_prepare(agent_, command, config, directory):
        a.manager.tick(root)  # the supervisor runs while the inputs are still on their way
        return {"modelPath": "/local/model", "datasetPath": "/local/data.json", "modelManifestPath": "/local/m.json"}

    monkeypatch.setattr("heteroes.study.prepare.prepare", slow_prepare)
    a.manager.accept({"assignmentId": "a" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "g"}})
    assert launched == []
    assert read_json(root / "config.json")["datasetPath"] == "/local/data.json"
    a.manager.tick(root)
    assert launched == [root]


def test_a_failed_input_transfer_fails_the_run_instead_of_holding_the_gpu_pool(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True

    def broken(*args):
        raise ValueError("Study transfer checksum mismatch")

    monkeypatch.setattr("heteroes.study.prepare.prepare", broken)
    cfg = _v3_config("f" * 32)
    with pytest.raises(ValueError, match="checksum"):
        a.manager.accept({"assignmentId": "a" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "g"}})
    state = a.manager.state(a.manager.directory(cfg["runId"]))
    assert state["status"] == "FAILED" and "checksum" in state["failureReason"]
    # the pool is free again: another run is accepted
    monkeypatch.setattr(
        "heteroes.study.prepare.prepare",
        lambda *args: {"modelPath": "/m", "datasetPath": "/d.json", "modelManifestPath": "/m.json"},
    )
    a.manager.accept(
        {"assignmentId": "b" * 32, "epoch": 1, "config": _v3_config("e" * 32), "computeGrants": {"test": "g"}}
    )


def test_a_failed_transfer_shows_no_foreign_error_text(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True

    def unreachable(*args):
        raise OSError("http://lab/grant?token=secret refused")

    monkeypatch.setattr("heteroes.study.prepare.prepare", unreachable)
    cfg = _v3_config("f" * 32)
    with pytest.raises(OSError):
        a.manager.accept({"assignmentId": "a" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "g"}})
    assert a.manager.state(a.manager.directory(cfg["runId"]))["failureReason"] == "OSError"


@pytest.mark.parametrize("status", ["FAILED", "PAUSED"])
def test_a_run_that_failed_before_its_workers_started_can_be_released(tmp_path, monkeypatch, status):
    # Found on the packaged r11 candidate2: the coordinator failed before any worker started, the agent reported
    # workerAlive=None for the device (coordinator and worker at once) and the lab kept the GPU reserved forever.
    a = agent(tmp_path)
    a.enabled = True
    cfg = _v3_config("f" * 32)
    monkeypatch.setattr(
        "heteroes.study.prepare.prepare",
        lambda *args: {"modelPath": "/m", "datasetPath": "/d.json", "modelManifestPath": "/m.json"},
    )
    a.manager.accept({"assignmentId": "a" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "g"}})
    root = a.manager.directory(cfg["runId"])
    a.manager.save(root, status=status)
    [report] = [p for p in a.observe() if p["assignmentId"] == "a" * 32]
    assert report["coordinatorAlive"] is False
    assert report["workerAlive"] is False  # no worker directory: no worker was ever started on this device


def test_a_running_coordinator_does_not_claim_its_workers_are_stopped(tmp_path, monkeypatch):
    a = agent(tmp_path)
    a.enabled = True
    cfg = _v3_config("f" * 32)
    monkeypatch.setattr(
        "heteroes.study.prepare.prepare",
        lambda *args: {"modelPath": "/m", "datasetPath": "/d.json", "modelManifestPath": "/m.json"},
    )
    a.manager.accept({"assignmentId": "a" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "g"}})
    a.manager.save(a.manager.directory(cfg["runId"]), status="RUNNING")
    [report] = [p for p in a.observe() if p["assignmentId"] == "a" * 32]
    assert report["workerAlive"] is None  # a START_WORKER may still be on its way


# ---- elastic membership (ADR-009): the lab's request becomes one line of membership-requests.json for the runner


def coordinating(tmp_path):
    a = agent(tmp_path)
    a.enabled = True
    cfg = {
        "runId": "b" * 32,
        "workerIds": ["test"],
        "workload": "arith16",
        "decodeEngine": "hf_generate",
        "maxGenerations": 3,
        "candidatesPerGeneration": 4,
        "alpha": 0.001,
        "sigma": 0.001,
        "schedulerPolicy": "greedy-tail",
        "syncMode": "synchronous",
        "backupPolicy": {"interval": 1, "retain": 3},
    }
    a.manager.accept({"assignmentId": "c" * 32, "epoch": 1, "config": cfg, "computeGrants": {"test": "private"}})
    return a, a.manager.directory(cfg["runId"])


def membership_command(command_id="m1", **change):
    body = {"changeId": "r1", "workerId": "late", "action": "JOIN", "actor": "owner", "grant": "late-private"}
    return {
        "commandId": command_id,
        "kind": "UPDATE_MEMBERSHIP",
        "assignmentId": "c" * 32,
        "epoch": 1,
        "change": {**body, **change},
    }


def test_the_agent_offers_membership_changes():
    from heteroes.product.agent import COMMAND_KINDS

    assert "UPDATE_MEMBERSHIP" in COMMAND_KINDS


def test_a_membership_change_is_written_once_for_the_runner(tmp_path):
    a, root = coordinating(tmp_path)
    a.handle(membership_command())
    a.handle(membership_command("m1-retried"))  # the same change delivered twice
    a.handle(membership_command("m2", changeId="r2", workerId="test", action="LEAVE", grant=None))
    requests = read_json(root / "membership-requests.json")["requests"]
    assert [(r["changeId"], r["workerId"], r["action"]) for r in requests] == [
        ("r1", "late", "JOIN"),
        ("r2", "test", "LEAVE"),
    ]
    assert "grant" not in requests[1]


@pytest.mark.parametrize(
    "change",
    [
        {"action": "ADD"},
        {"changeId": ""},
        {"workerId": 3},
        {"grant": ""},
        {"actor": None},
        {"extra": "x"},
    ],
)
def test_a_malformed_membership_change_is_refused_without_a_trace(tmp_path, change):
    a, root = coordinating(tmp_path)
    with pytest.raises(InvalidCommand):
        a.handle(membership_command(**change))
    assert not (root / "membership-requests.json").exists()


def test_a_change_for_an_assignment_not_here_yet_waits(tmp_path):
    a = agent(tmp_path)
    a.enabled = True
    with pytest.raises(RuntimeError, match="assignment"):
        a.handle(membership_command())
