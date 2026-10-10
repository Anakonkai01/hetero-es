"""Control-plane tests exercise ownership and projections without acquiring a GPU."""
import json
from pathlib import Path

import pytest

from heteroes.product.files import read_json, write_json
from heteroes.product.gateway import Manager, validate
from heteroes.product import gateway, remote
from test_coordinator import Env


def config(run_id="a" * 32, **changes):
    return {"runId": run_id, "maxGenerations": 3, "candidatesPerGeneration": 8, "alpha": .001, "sigma": .001,
            "workload": "arith16", "decodeEngine": "hf_generate", "workerIds": ["local"],
            "schedulerPolicy": "greedy", "syncMode": "synchronous", **changes}


@pytest.fixture
def manager(tmp_path):
    workers = [{"id": name, "label": name, "python": "/python", "source": "/source", "modelPath": "/model",
                "stateDirectory": str(tmp_path / "workers" / name)} for name in ("local", "remote")]
    return Manager({"stateDirectory": str(tmp_path / "runs"), "modelPath": "/pinned-model", "workerHost": "127.0.0.1",
                    "workerPort": 8765, "workerUrl": "http://127.0.0.1:8765", "workers": workers}, "private-token")


def test_submission_is_idempotent_and_single_owner(manager):
    manager.submit(config())
    manager.submit(config())
    with pytest.raises(ValueError, match="different"):
        manager.submit(config(alpha=.002))
    with pytest.raises(RuntimeError, match="owns"):
        manager.submit(config("b" * 32))
    root = manager.directory("a" * 32)
    manager.save(root, status="COMPLETED")
    manager.submit(config("b" * 32))


@pytest.mark.parametrize("changes", [{"runId": "../escape"}, {"workerIds": ["other"]}, {"workerIds": ["local", "local"]},
    {"alpha": float("nan")}, {"sigma": float("inf")}, {"maxGenerations": True}, {"candidatesPerGeneration": 1},
    {"schedulerPolicy": "capacity-weighted"}, {"syncMode": "asynchronous"}])
def test_bad_runtime_configuration_never_launches(manager, changes):
    with pytest.raises(ValueError):
        manager.submit(config(**changes))
    assert list(manager.root.iterdir()) == []


def prepare(manager, monkeypatch, workers=("local",)):
    manager.submit(config(workerIds=list(workers)))
    root = manager.directory("a" * 32)
    write_json(root / "process.json", {"pid": 123, "birth": "owned"})
    write_json(root / "runner.json", {"status": "PREPARING"})
    monkeypatch.setattr(gateway, "alive", lambda record: True)
    return root


def test_offline_preflight_never_claims_unstarted_worker(manager, monkeypatch):
    root = prepare(manager, monkeypatch, ("local", "remote"))
    def call(worker, request):
        if worker["id"] == "remote":
            raise RuntimeError("SSH offline before launch")
        return {"ready": True, "alive": True, "events": []}
    monkeypatch.setattr(manager, "remote", call)
    manager.tick(root)
    assert (root / "start.flag").exists()
    assert manager.state(root)["workerStates"]["remote"]["notStarted"]
    assert any("remote" in line and "worker_unavailable" in line for line in (root / "lifecycle.jsonl").read_text().splitlines())


def test_uncertain_shutdown_blocks_pool_release(manager, monkeypatch):
    root = prepare(manager, monkeypatch)
    manager.save(root, workersLaunched=True, workerStates={"local": {"alive": True, "ready": True, "confirmed": True}})
    write_json(root / "runner.json", {"status": "CANCELLED"})
    monkeypatch.setattr(manager, "remote", lambda *_: (_ for _ in ()).throw(RuntimeError("SSH vanished")))
    manager.tick(root)
    assert manager.state(root)["status"] == "CANCELLING"
    assert not (root / "workers-stopped.flag").exists()
    with pytest.raises(RuntimeError):
        manager.submit(config("b" * 32))
    monkeypatch.setattr(manager, "remote", lambda *_: {"alive": False, "ready": True, "events": []})
    monkeypatch.setattr(gateway, "alive", lambda _: False)
    manager.tick(root)
    assert manager.state(root)["status"] == "CANCELLED"
    assert (root / "workers-stopped.flag").exists()


def test_only_one_automatic_coordinator_recovery(manager, monkeypatch):
    root = prepare(manager, monkeypatch)
    write_json(root / "runner.json", {"status": "RUNNING"})
    monkeypatch.setattr(gateway, "alive", lambda _: False)
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
    monkeypatch.setattr(manager, "remote", lambda *_: {"alive": False, "ready": True,
        "events": [{"event": "exit", "reason": "quarantined"}]})
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
