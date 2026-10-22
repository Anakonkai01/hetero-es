"""Agent supervisor ownership and ledger projections, without acquiring a GPU."""

import json
import urllib.error

import pytest

from heteroes.product.files import read_json, write_json
from heteroes.product import agent as agent_module, run_supervisor, remote
from test_device_agent import agent
from test_coordinator import Env


def config(run_id="a" * 32, **changes):
    return {
        "runId": run_id,
        "maxGenerations": 3,
        "candidatesPerGeneration": 8,
        "alpha": 0.001,
        "sigma": 0.001,
        "workload": "arith16",
        "decodeEngine": "hf_generate",
        "workerIds": ["local"],
        "schedulerPolicy": "greedy",
        "syncMode": "synchronous",
        **changes,
    }


@pytest.fixture
def manager(tmp_path):
    device = agent(tmp_path)
    device.enabled = True
    device.manager.workers = {name: {"id": name} for name in ("local", "remote")}
    return device.manager


def test_submission_is_idempotent_and_single_owner(manager):
    manager.submit(config())
    manager.submit(config())
    with pytest.raises(ValueError, match="different"):
        manager.submit(config(alpha=0.002))
    with pytest.raises(RuntimeError, match="owns"):
        manager.submit(config("b" * 32))
    root = manager.directory("a" * 32)
    manager.save(root, status="COMPLETED")
    manager.submit(config("b" * 32))


@pytest.mark.parametrize(
    "changes",
    [
        {"runId": "../escape"},
        {"workerIds": ["other"]},
        {"workerIds": ["local", "local"]},
        {"alpha": float("nan")},
        {"sigma": float("inf")},
        {"maxGenerations": True},
        {"candidatesPerGeneration": 1},
        {"schedulerPolicy": "capacity-weighted"},
        {"schedulerPolicy": "round-robin"},
        {"schedulerPolicy": None},
        {"syncMode": "asynchronous"},
    ],
)
def test_bad_runtime_configuration_never_launches(manager, changes):
    with pytest.raises(ValueError):
        manager.submit(config(**changes))
    assert list(manager.root.iterdir()) == []


@pytest.mark.parametrize("policy", ["greedy-tail", "greedy"])
def test_both_offered_scheduling_policies_are_accepted(manager, policy):
    manager.submit(config(schedulerPolicy=policy))
    assert [path.name for path in manager.root.iterdir()] == ["a" * 32]


def prepare(manager, monkeypatch, workers=("local",)):
    manager.submit(config(workerIds=list(workers)))
    root = manager.directory("a" * 32)
    write_json(root / "process.json", {"pid": 123, "birth": "owned"})
    write_json(root / "runner.json", {"status": "PREPARING"})
    write_json(root / "assignment.json", {"config": {"workerIds": list(workers)}})
    monkeypatch.setattr(run_supervisor, "alive", lambda record: True)
    monkeypatch.setattr(agent_module, "alive", lambda record: True)
    return root


def test_offline_preflight_never_claims_unstarted_worker(manager, monkeypatch):
    root = prepare(manager, monkeypatch, ("local", "remote"))

    def call(worker, request):
        if worker["id"] == "remote":
            raise RuntimeError("Agent offline before launch")
        return {"ready": True, "alive": True, "events": []}

    monkeypatch.setattr(manager, "remote", call)
    manager.tick(root)
    assert (root / "start.flag").exists()
    assert manager.state(root)["workerStates"]["remote"]["notStarted"]
    assert any(
        "remote" in line and "worker_unavailable" in line
        for line in (root / "lifecycle.jsonl").read_text().splitlines()
    )


def test_long_healthy_run_is_not_cancelled_by_historical_budget(manager, monkeypatch):
    root = prepare(manager, monkeypatch)
    manager.save(
        root,
        startedAt=run_supervisor.time.time() - 3600,
        workersLaunched=True,
        workerStates={"local": {"alive": True, "ready": True, "confirmed": True}},
    )
    write_json(root / "runner.json", {"status": "RUNNING"})
    monkeypatch.setattr(manager, "remote", lambda *_: {"alive": True, "ready": True, "events": []})
    manager.tick(root)
    assert manager.state(root)["status"] == "RUNNING"
    assert not (root / "cancel.flag").exists()


def test_uncertain_shutdown_blocks_pool_release(manager, monkeypatch):
    root = prepare(manager, monkeypatch)
    manager.save(root, workersLaunched=True, workerStates={"local": {"alive": True, "ready": True, "confirmed": True}})
    write_json(root / "runner.json", {"status": "CANCELLED"})
    monkeypatch.setattr(manager, "remote", lambda *_: (_ for _ in ()).throw(RuntimeError("Agent vanished")))
    manager.tick(root)
    assert manager.state(root)["status"] == "CANCELLING"
    assert not (root / "workers-stopped.flag").exists()
    with pytest.raises(RuntimeError):
        manager.submit(config("b" * 32))
    monkeypatch.setattr(manager, "remote", lambda *_: {"alive": False, "ready": True, "events": []})
    monkeypatch.setattr(run_supervisor, "alive", lambda _: False)
    monkeypatch.setattr(agent_module, "alive", lambda _: False)
    manager.tick(root)
    assert manager.state(root)["status"] == "CANCELLED"
    assert (root / "workers-stopped.flag").exists()


def test_a_worker_unreachable_for_long_no_longer_holds_a_finished_run(manager, monkeypatch):
    # GSM8K demo tier 2b, 2026-10-21: two worker machines died; the finished run stayed DRAINING until one came back
    root = prepare(manager, monkeypatch, ("local", "remote"))
    states = {name: {"alive": True, "ready": True, "confirmed": True} for name in ("local", "remote")}
    manager.save(root, workersLaunched=True, workerStates=states)
    write_json(root / "runner.json", {"status": "COMPLETED"})
    monkeypatch.setattr(run_supervisor, "alive", lambda _: False)

    def call(worker, request):
        if worker["id"] == "remote":
            raise RuntimeError("Agent vanished")
        return {"alive": False, "ready": True, "events": []}

    monkeypatch.setattr(manager, "remote", call)
    manager.tick(root)
    assert manager.state(root)["status"] == "DRAINING"  # a short absence still blocks (uncertain shutdown)
    remote_state = manager.state(root)["workerStates"]["remote"]
    remote_state["unreachableSince"] -= run_supervisor.UNREACHABLE_STOP_SECONDS - 60
    manager.save(root, workerStates={**manager.state(root)["workerStates"], "remote": remote_state})
    manager.tick(root)
    assert manager.state(root)["status"] == "DRAINING"
    remote_state["unreachableSince"] -= 61
    manager.save(root, workerStates={**manager.state(root)["workerStates"], "remote": remote_state})
    manager.tick(root)
    assert manager.state(root)["status"] == "COMPLETED"
    assert manager.state(root)["workerStates"]["remote"]["lost"]
    assert "worker_lost" in (root / "lifecycle.jsonl").read_text()


def test_only_one_automatic_coordinator_recovery(manager, monkeypatch):
    root = prepare(manager, monkeypatch)
    write_json(root / "runner.json", {"status": "RUNNING"})
    monkeypatch.setattr(run_supervisor, "alive", lambda _: False)
    monkeypatch.setattr(agent_module, "alive", lambda _: False)

    def launch(root):
        write_json(root / "process.json", {"pid": 999, "birth": "owned"})

    monkeypatch.setattr(manager, "launch", launch)
    manager.tick(root)
    assert manager.state(root)["recoveryCount"] == 1
    manager.tick(root)
    assert manager.state(root)["status"] == "FAILED"


def test_unknown_birth_time_and_reused_pid_are_never_signalled(tmp_path, monkeypatch):
    monkeypatch.setattr(remote, "identity", lambda _: None)
    assert not remote.alive({"pid": 123, "birth": None})
    monkeypatch.setattr(remote, "identity", lambda _: "new-birth")
    root = tmp_path / "worker"
    write_json(root / "process.json", {"pid": 123, "birth": "old-birth"})
    monkeypatch.setattr(remote.os, "kill", lambda *_: pytest.fail("signalled an unrelated process"))
    assert remote.handle({"action": "stop", "directory": str(root)})["alive"] is False


def test_wsl_worker_uses_matching_windows_jit_library(tmp_path, monkeypatch):
    wsl = tmp_path / "wsl"
    (wsl / "lib").mkdir(parents=True)
    active = wsl / "drivers" / "active"
    old = wsl / "drivers" / "old"
    active.mkdir(parents=True)
    old.mkdir()
    (wsl / "lib" / "libnvidia-gpucomp.so").write_bytes(b"active")
    # WSL exposes the same Windows file through different mount device IDs.
    (active / "libnvidia-gpucomp.so").write_bytes(b"active")
    (old / "libnvidia-gpucomp.so").write_bytes(b"old")
    (active / "libnvidia-ptxjitcompiler.so.1").write_bytes(b"jit")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing")
    result = remote.worker_environment("/source", "secret", wsl)
    assert result["LD_LIBRARY_PATH"] == f"{wsl / 'lib'}:{active}:/existing"
    assert result["PATH"].startswith(str(wsl / "lib") + ":")
    assert result["PYTHONPATH"] == "/source"


def test_wsl_worker_rejects_ambiguous_driver_and_preserves_linux_environment(tmp_path, monkeypatch):
    wsl = tmp_path / "wsl"
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing")
    assert remote.worker_environment("/source", "secret", wsl)["LD_LIBRARY_PATH"] == "/existing"
    (wsl / "lib").mkdir(parents=True)
    (wsl / "lib" / "libnvidia-gpucomp.so").write_bytes(b"active")
    with pytest.raises(RuntimeError, match="matching WSL"):
        remote.worker_environment("/source", "secret", wsl)


def test_restore_mismatch_quarantine_survives_run_completion(manager, monkeypatch):
    root = prepare(manager, monkeypatch)
    manager.save(root, workerStates={"local": {"alive": True, "ready": True, "confirmed": True}})
    monkeypatch.setattr(
        manager,
        "remote",
        lambda *_: {"alive": False, "ready": True, "events": [{"event": "exit", "reason": "quarantined"}]},
    )
    assert manager.poll_workers(root)
    manager.save(root, status="FAILED")
    with pytest.raises(ValueError, match="quarantined"):
        manager.submit(config("b" * 32))
    # Idempotent observation of the original run remains possible.
    assert manager.submit(config())["status"] == "FAILED"


def test_projection_preserves_seed_string_and_hides_lease_tokens(manager, tmp_path):
    # A real toy coordinator ledger, including a real accepted result and update.
    root = manager.directory("a" * 32)
    manager.submit(config())
    env = Env(tmp_path / "toy")
    env.start_workers()
    try:
        env.coordinator.run(1)
        import sqlite3

        with sqlite3.connect(root / "ledger.sqlite") as destination:
            env.ledger._db.backup(destination)
        result = manager.snapshot("a" * 32)
        assert result["generations"][0]["committedCandidateCount"] == 4
        assert all(isinstance(item["seed"], str) for item in result["candidates"])
        assert len(result["attempts"]) >= 4
        serialized = json.dumps(result)
        for forbidden in ("lease_token", "leaseToken", "private-token"):
            assert forbidden not in serialized
        assert all(item["status"] == "SUCCEEDED" for item in result["attempts"])
    finally:
        env.close()


def test_the_audit_summary_shows_how_many_audits_were_chosen_not_only_completed(manager, tmp_path):
    # ADR-009 (F9): a timed-out audit drain only logged audit_incomplete; the summary must show the gap
    root = manager.directory("a" * 32)
    manager.submit(config())
    env = Env(tmp_path / "toy")
    env.start_workers()
    try:
        env.coordinator.run(1)
        import sqlite3

        with sqlite3.connect(root / "ledger.sqlite") as destination:
            env.ledger._db.backup(destination)
        with (root / "events.jsonl").open("a") as log:
            for generation, selected, completed in ((0, 2, 2), (1, 1, 0)):
                event = {"event": "generation_done", "generation": generation}
                log.write(json.dumps({**event, "audits": {"selected": selected, "completed": completed}}) + "\n")
            log.write(json.dumps({"event": "generation_done", "generation": 2}) + "\n")  # an older run: no counts
        summary = manager.snapshot("a" * 32)["auditSummary"]
        assert summary["selected"] == 3 and summary["completed"] == 0  # the toy ledger itself holds no audit rows
    finally:
        env.close()


# ---- elastic membership (ADR-009): the runner writes membership.json at each boundary, the supervisor follows it


def running_with(manager, monkeypatch, members, left=(), states=None):
    root = prepare(manager, monkeypatch, ("local",))
    manager.save(
        root,
        workersLaunched=True,
        workerStates=states or {"local": {"alive": True, "ready": True, "confirmed": True}},
    )
    write_json(root / "runner.json", {"status": "RUNNING"})
    write_json(root / "membership.json", {"generation": 10, "members": list(members), "left": list(left)})
    calls, stopped = [], set()

    def call(worker, request):  # a stopped worker process stays stopped when it is polled
        calls.append((worker["id"], request["action"]))
        if request["action"] == "stop":
            stopped.add(worker["id"])
        return {"alive": worker["id"] not in stopped, "ready": True, "events": []}

    monkeypatch.setattr(manager, "remote", call)
    return root, calls


def test_a_worker_that_joined_is_started_while_the_run_goes_on(manager, monkeypatch):
    root, calls = running_with(manager, monkeypatch, ["local", "late"])
    manager.tick(root)
    assert ("late", "probe") in calls and ("late", "start") in calls
    assert manager.state(root)["workerStates"]["late"] == {"alive": True, "confirmed": True, "ready": True}
    calls.clear()
    manager.tick(root)  # started once, then only polled
    assert ("late", "start") not in calls and ("late", "poll") in calls


def test_a_worker_that_left_is_stopped_and_not_started_again(manager, monkeypatch):
    states = {
        "local": {"alive": True, "ready": True, "confirmed": True},
        "late": {"alive": True, "ready": True, "confirmed": True},
    }
    root, calls = running_with(manager, monkeypatch, ["local"], left=["late"], states=states)
    manager.tick(root)
    assert ("late", "stop") in calls and ("late", "start") not in calls
    late = manager.state(root)["workerStates"]["late"]
    assert (late["alive"], late["confirmed"], late["left"]) == (False, True, True)
    assert manager.state(root)["status"] == "RUNNING"
    calls.clear()
    manager.tick(root)  # the lab may already have given its GPU to another run: it is not asked about this one again
    assert [call for call in calls if call[0] == "late"] == []
    snapshot = manager.snapshot(root.name)
    assert snapshot["membership"]["left"] == ["late"] and snapshot["state"]["workerStates"]["late"]["left"] is True


def test_a_left_worker_whose_stop_cannot_be_confirmed_is_not_logged_as_left_every_tick(manager, monkeypatch):
    # GSM8K demo tier 2c: the lab refused the stop of a worker it had already released; worker_left was logged per tick
    states = {
        "local": {"alive": True, "ready": True, "confirmed": True},
        "late": {"alive": True, "ready": True, "confirmed": False},
    }
    root, calls = running_with(manager, monkeypatch, ["local"], left=["late"], states=states)

    def call(worker, request):
        if worker["id"] == "late":
            raise RuntimeError("Device is not authorized for this assignment")
        return {"alive": True, "ready": True, "events": []}

    monkeypatch.setattr(manager, "remote", call)
    for _ in range(3):
        manager.tick(root)
    log = root / "lifecycle.jsonl"
    assert not log.exists() or "worker_left" not in log.read_text()


def test_a_quarantined_worker_that_joins_is_not_started(manager, monkeypatch):
    root, calls = running_with(manager, monkeypatch, ["local", "late"])
    write_json(manager.root / "quarantine.json", {"late": {"runId": "x", "t": 1}})
    manager.tick(root)
    assert ("late", "start") not in calls
    assert manager.state(root)["workerStates"]["late"]["notStarted"] is True


def test_a_worker_that_was_already_stopped_when_it_left_is_marked_without_a_stop(manager, monkeypatch):
    states = {
        "local": {"alive": True, "ready": True, "confirmed": True},
        "late": {"alive": False, "ready": True, "confirmed": True},  # its owner turned it OFF before the boundary
    }
    root, calls = running_with(manager, monkeypatch, ["local"], left=["late"], states=states)
    manager.tick(root)
    assert ("late", "stop") not in calls
    assert manager.state(root)["workerStates"]["late"]["left"] is True


# ---- a member whose worker stopped while the run goes on is started again, as a new launch


def restarting(manager, monkeypatch, states, members=("local", "late"), probe=lambda worker: True):
    root, _ = running_with(manager, monkeypatch, members, states=states)
    clock = [1000.0]
    monkeypatch.setattr(run_supervisor.time, "time", lambda: clock[0])
    calls, polls, running = [], [], {w for w, value in states.items() if value.get("alive") and value.get("confirmed")}

    def call(worker, request):  # a dead worker process stays dead until it is started again
        action = request["action"]
        (polls if action == "poll" else calls).append((worker["id"], action, request.get("launch", 0)))
        if action == "probe" and not probe(worker["id"]):
            raise RuntimeError("Worker contribution is OFF")
        {"start": running.add, "stop": running.discard}.get(action, lambda _: None)(worker["id"])
        return {"alive": worker["id"] in running, "ready": True, "events": []}

    monkeypatch.setattr(manager, "remote", call)
    return root, calls, clock, polls


ALIVE = {"alive": True, "ready": True, "confirmed": True}


def blocked_member(manager, monkeypatch):
    root, calls, clock, polls = restarting(manager, monkeypatch, {"local": ALIVE, "late": ALIVE})
    relay = manager.remote

    def remote(worker, request):
        if worker["id"] == "late" and request["action"] == "poll":
            return {"alive": False, "ready": True, "events": [{"event": "exit", "reason": "needs_private_route"}]}
        return relay(worker, request)

    monkeypatch.setattr(manager, "remote", remote)
    manager.tick(root)
    return root, calls, clock


def test_private_route_failure_blocks_only_that_member_and_never_restarts(manager, monkeypatch):
    root, calls, clock = blocked_member(manager, monkeypatch)
    for _ in range(6):
        clock[0] += run_supervisor.RESTART_SECONDS
        manager.tick(root)
    assert not [call for call in calls if call[0] == "late" and call[1] == "start"]
    state = manager.state(root)
    assert state["status"] == "RUNNING" and state["workerStates"]["local"]["alive"]
    assert state["workerStates"]["late"]["stopReason"] == "needs_private_route"
    assert read_json(root / "worker-blocks.json")["late"]["reason"] == "needs_private_route"
    assert not (manager.root / "quarantine.json").exists()
    events = [json.loads(line) for line in (root / "lifecycle.jsonl").read_text().splitlines()]
    assert sum(e["event"] == "worker_blocked" for e in events) == 1


def test_block_survives_transient_state_reset_and_rejoin(manager, monkeypatch):
    root, calls, clock = blocked_member(manager, monkeypatch)
    manager.save(root, workerStates={"local": ALIVE})
    manager._follow_membership(root, manager.state(root))
    assert manager.state(root)["workerStates"]["late"]["stopReason"] == "needs_private_route"
    manager._start_one(root, "late", {}, 1)
    assert not [call for call in calls if call[0] == "late" and call[1] == "start"]


def test_explicit_retry_is_idempotent_and_same_failure_blocks_again(manager, monkeypatch):
    root, calls, clock = blocked_member(manager, monkeypatch)
    manager.retry_worker(root, "late", "retry-1")
    clock[0] += run_supervisor.RESTART_SECONDS
    manager.tick(root)
    assert len([call for call in calls if call[0] == "late" and call[1] == "start"]) == 1
    assert manager.state(root)["workerStates"]["late"]["stopReason"] == "needs_private_route"
    manager.retry_worker(root, "late", "retry-1")
    for _ in range(3):
        clock[0] += run_supervisor.RESTART_SECONDS
        manager.tick(root)
    assert len([call for call in calls if call[0] == "late" and call[1] == "start"]) == 1


def test_a_member_whose_worker_died_is_started_again_once_its_device_is_on(manager, monkeypatch):
    back = []
    states = {"local": ALIVE, "late": {"alive": False, "ready": True, "confirmed": True}}
    root, calls, clock, polls = restarting(manager, monkeypatch, states, probe=lambda worker: worker in back)
    manager.tick(root)  # its device is still away or OFF: asked, nothing started
    assert ("late", "probe", 0) in calls and not [c for c in calls if c[1] == "start"]
    calls.clear()
    back.append("late")
    manager.tick(root)  # not asked again at once
    assert ("late", "probe", 0) not in calls
    clock[0] += run_supervisor.RESTART_SECONDS
    manager.tick(root)
    assert ("late", "start", 1) in calls and polls[-1] == ("late", "poll", 1)  # a new launch, polled as that one
    assert manager.state(root)["workerStates"]["late"] == {**ALIVE, "launch": 1}
    assert any('"worker_restarted"' in line for line in (root / "lifecycle.jsonl").read_text().splitlines())
    calls.clear()
    clock[0] += run_supervisor.RESTART_SECONDS
    manager.tick(root)  # running again: only polled
    assert [c for c in calls if c[0] == "late"] == []


def test_a_member_not_started_again_says_why_once_per_reason(manager, monkeypatch):
    # c8 run, 2026-10-21: the 1660S was refused at every probe and nothing said so
    refusals = [403, 403, 409]  # not in the assignment twice, then OFF
    states = {"local": ALIVE, "late": {"alive": False, "ready": True, "confirmed": True}}
    root, calls, clock, polls = restarting(manager, monkeypatch, states)
    relay = manager.remote

    def remote(worker, request):
        if request["action"] == "probe" and refusals:
            raise urllib.error.HTTPError("http://lab", refusals.pop(0), "refused", None, None)
        return relay(worker, request)

    monkeypatch.setattr(manager, "remote", remote)
    for _ in range(4):
        manager.tick(root)
        clock[0] += run_supervisor.RESTART_SECONDS
    events = [json.loads(line) for line in (root / "lifecycle.jsonl").read_text().splitlines()]
    deferred = [
        (e["worker_id"], e["launch"], e["httpStatus"]) for e in events if e["event"] == "worker_restart_deferred"
    ]
    assert deferred == [("late", 1, 403), ("late", 1, 409)]
    assert [e["event"] for e in events][-1] == "worker_restarted"
    # it dies again and is refused for the same reason as before: that is a new story, said again
    states = manager.state(root)["workerStates"]
    manager.save(root, workerStates={**states, "late": {**states["late"], "alive": False}})
    refusals.append(409)
    manager.tick(root)
    events = [json.loads(line) for line in (root / "lifecycle.jsonl").read_text().splitlines()]
    assert (events[-1]["event"], events[-1]["launch"], events[-1]["httpStatus"]) == ("worker_restart_deferred", 2, 409)


def test_a_worker_away_at_preparation_gets_its_first_launch_when_it_comes_back(manager, monkeypatch):
    away = {"notStarted": True, "alive": False, "ready": False, "confirmed": True}
    root, calls, *_ = restarting(manager, monkeypatch, {"local": ALIVE, "late": away})
    manager.tick(root)
    assert ("late", "start", 0) in calls and manager.state(root)["workerStates"]["late"] == ALIVE


def test_a_worker_added_back_after_it_left_starts_after_its_last_launch(manager, monkeypatch):
    gone = {"alive": False, "ready": True, "confirmed": True, "launch": 2, "left": True}
    root, calls, *_ = restarting(manager, monkeypatch, {"local": ALIVE, "late": gone})
    manager.tick(root)
    assert ("late", "start", 3) in calls and manager.state(root)["workerStates"]["late"] == {**ALIVE, "launch": 3}
    # tier 2e: it was logged `worker_restarted`, so the timeline never showed the member coming back (finding 9)
    events = [json.loads(line) for line in (root / "lifecycle.jsonl").read_text().splitlines()]
    assert [(e["event"], e.get("rejoin")) for e in events if e["worker_id"] == "late"] == [("worker_joined", True)]


def test_a_member_not_answering_during_the_run_is_said_once_and_again_when_it_is_back(manager, monkeypatch):
    # tier 3, 2026-10-22: the 1660S was unreachable for 2 h 13 min and the coordinator logged nothing (finding 11)
    root, calls, clock, polls = restarting(manager, monkeypatch, {"local": ALIVE, "late": ALIVE})
    relay, away = manager.remote, [True]

    def remote(worker, request):
        if worker["id"] == "late" and away[0]:
            raise RuntimeError("timed out")
        return relay(worker, request)

    monkeypatch.setattr(manager, "remote", remote)

    def said():
        log = root / "lifecycle.jsonl"
        return [json.loads(line)["event"] for line in log.read_text().splitlines()] if log.exists() else []

    manager.tick(root)
    clock[0] += run_supervisor.UNREACHABLE_NOTICE_SECONDS - 1
    manager.tick(root)
    assert "worker_unreachable" not in said()  # a short silence is not news
    for _ in range(3):
        clock[0] += run_supervisor.UNREACHABLE_NOTICE_SECONDS
        manager.tick(root)
    assert said().count("worker_unreachable") == 1
    late = manager.state(root)["workerStates"]["late"]
    assert late["confirmed"] is False and late["unreachableSince"] == 1000.0
    assert not [c for c in calls if c[0] == "late" and c[1] == "start"]  # never started beside a process it cannot see
    away[0] = False
    manager.tick(root)
    assert said()[-1] == "worker_reachable" and manager.state(root)["workerStates"]["late"] == ALIVE


@pytest.mark.parametrize(
    "late",
    [
        {"alive": True, "ready": False, "confirmed": False},  # unknown: it may still run
        {"alive": False, "ready": True, "confirmed": False},  # last seen stopped, not confirmed now
    ],
)
def test_a_worker_whose_state_is_unknown_is_never_started_beside_itself(manager, monkeypatch, late):
    root, calls, *_ = restarting(manager, monkeypatch, {"local": ALIVE, "late": late})
    monkeypatch.setattr(manager, "poll_workers", lambda root, stop=False: False)
    manager.tick(root)
    assert [c for c in calls if c[0] == "late"] == []


def test_quarantined_and_departed_workers_are_not_started_again(manager, monkeypatch):
    dead = {"alive": False, "ready": True, "confirmed": True}
    states = {"local": ALIVE, "bad": dict(dead), "gone": {**dead, "left": True}}
    root, calls, *_ = restarting(manager, monkeypatch, states, members=("local", "bad"))
    write_json(manager.root / "quarantine.json", {"bad": {"runId": "x", "t": 1}})
    manager.tick(root)
    assert [c for c in calls if c[0] != "local"] == []


def test_a_worker_that_keeps_dying_is_left_alone_after_the_last_launch(manager, monkeypatch):
    last = run_supervisor.MAX_LAUNCHES - 1
    states = {"local": ALIVE, "late": {"alive": False, "ready": True, "confirmed": True, "launch": last}}
    root, calls, clock, polls = restarting(manager, monkeypatch, states)
    for _ in range(2):
        manager.tick(root)
        clock[0] += run_supervisor.RESTART_SECONDS
    assert [c for c in calls if c[0] == "late"] == []
    lines = (root / "lifecycle.jsonl").read_text().splitlines()
    assert sum('"worker_restart_limit"' in line for line in lines) == 1


def test_a_start_whose_outcome_is_unknown_says_why(manager, monkeypatch):
    # candidate13 acceptance: two starts were "unknown" and nothing said whether the lab refused or just had not seen it
    root, calls, clock, polls = restarting(manager, monkeypatch, {"local": ALIVE})
    refusal = urllib.error.HTTPError("http://lab", 403, "refused", None, None)
    monkeypatch.setattr(manager, "start_worker", lambda *a, **k: (_ for _ in ()).throw(refusal))
    manager._launch_worker(root, "remote", {}, 0, 0)
    event = json.loads((root / "lifecycle.jsonl").read_text().splitlines()[-1])
    assert (event["event"], event["error"], event["httpStatus"]) == ("worker_start_unknown", "HTTPError", 403)


def test_explicit_retry_can_launch_once_after_the_automatic_limit(manager, monkeypatch):
    root, calls, clock = blocked_member(manager, monkeypatch)
    states = manager.state(root)["workerStates"]
    states["late"]["launch"] = run_supervisor.MAX_LAUNCHES - 1
    manager.save(root, workerStates=states)
    manager.retry_worker(root, "late", "retry-limit")
    manager.tick(root)
    starts = [call for call in calls if call[0] == "late" and call[1] == "start"]
    assert len(starts) == 1
    assert starts[0][2] == run_supervisor.MAX_LAUNCHES
    clock[0] += run_supervisor.RESTART_SECONDS
    manager.tick(root)
    assert len([call for call in calls if call[0] == "late" and call[1] == "start"]) == 1


def test_pending_explicit_retry_does_not_reconsume_the_old_exit_when_probe_is_away(manager, monkeypatch):
    root, calls, clock = blocked_member(manager, monkeypatch)
    manager.retry_worker(root, "late", "retry-offline")
    relay = manager.remote

    def away(worker, request):
        if worker["id"] == "late" and request["action"] == "probe":
            raise RuntimeError("away")
        return relay(worker, request)

    monkeypatch.setattr(manager, "remote", away)
    manager.tick(root)
    assert read_json(root / "worker-blocks.json") == {}
    assert manager.state(root)["workerStates"]["late"]["retryPending"]
    monkeypatch.setattr(manager, "remote", relay)
    clock[0] += run_supervisor.RESTART_SECONDS
    manager.tick(root)
    assert len([call for call in calls if call[0] == "late" and call[1] == "start"]) == 1
    assert manager.state(root)["workerStates"]["late"]["stopReason"] == "needs_private_route"


def test_a_persistent_block_keeps_the_launch_identity_after_process_state_is_cleared(manager, monkeypatch):
    root, calls, clock = blocked_member(manager, monkeypatch)
    block = read_json(root / "worker-blocks.json")
    block["late"]["launch"] = 7
    write_json(root / "worker-blocks.json", block)
    manager.save(root, workerStates={})
    manager._start_one(root, "late", {}, 0)
    manager.retry_worker(root, "late", "retry-after-resume")
    manager.tick(root)
    assert ("late", "start", 8) in calls


def test_a_start_lost_on_the_way_to_the_lab_is_sent_again_with_the_same_launch(manager, monkeypatch):
    # overnight 2026-10-23: the edge timed out on two START requests; the lab never queued them, every poll answered
    # "waiting for worker acknowledgement" and the run stayed STARTING. The lab ignores a repeated start (dedupe key).
    root, calls, clock, polls = restarting(manager, monkeypatch, {"local": ALIVE})
    relay, lost = manager.remote, [True]
    started, sent = set(), []

    def remote(worker, request):
        if worker["id"] == "late":
            sent.append((request["action"], request.get("launch", 0)))
            if request["action"] == "start":
                if lost[0]:
                    lost[0] = False
                    raise urllib.error.URLError("timed out")
                started.add(request.get("launch", 0))
            elif request["action"] == "poll" and not started:
                raise RuntimeError("HTTP 503 Waiting for worker acknowledgement")
        return relay(worker, request)

    monkeypatch.setattr(manager, "remote", remote)
    manager.workers["late"] = {"id": "late"}
    manager._launch_worker(root, "late", manager.state(root)["workerStates"], 0, 0)
    assert manager.state(root)["workerStates"]["late"]["startUnconfirmed"] is True
    manager.poll_workers(root)
    assert sent == [("start", 0), ("poll", 0), ("start", 0)]
    assert manager.state(root)["workerStates"]["late"] == ALIVE
    away = [True]
    relay_after = manager.remote

    def unreachable(worker, request):  # confirmed once: a silence later is never answered with a start
        if worker["id"] == "late" and away[0]:
            sent.append((request["action"], request.get("launch", 0)))
            raise RuntimeError("timed out")
        return relay_after(worker, request)

    monkeypatch.setattr(manager, "remote", unreachable)
    manager.poll_workers(root)
    manager.poll_workers(root, stop=True)
    assert sent.count(("start", 0)) == 2


def test_a_stop_never_resends_a_lost_start(manager, monkeypatch):
    root, calls, clock, polls = restarting(manager, monkeypatch, {"local": ALIVE})
    relay, sent = manager.remote, []

    def remote(worker, request):
        if worker["id"] == "late":
            sent.append(request["action"])
            if request["action"] in ("start", "stop"):
                raise urllib.error.URLError("timed out")
        return relay(worker, request)

    monkeypatch.setattr(manager, "remote", remote)
    manager.workers["late"] = {"id": "late"}
    manager._launch_worker(root, "late", manager.state(root)["workerStates"], 0, 0)
    manager.poll_workers(root, stop=True)
    assert sent == ["start", "stop"]
