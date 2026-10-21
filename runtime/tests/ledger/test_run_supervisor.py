"""Agent supervisor ownership and ledger projections, without acquiring a GPU."""

import json

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
