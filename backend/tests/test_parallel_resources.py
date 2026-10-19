"""Physical alias fencing and eligible FIFO on independent CPU fake devices."""

from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest
from backend.devices import AgentRuntime
from backend.store import Store
from labkit import boot, enable, pair, queued


def same_gpu(lab, device, auth, source):
    client, _, runtime, _ = lab
    profile = next(d["selfTest"] for d in runtime.devices() if d["deviceId"] == source["deviceId"])
    boot(client, auth, "boot-1", selfTest=profile)


def config(store, run_id):
    body = store.get(run_id)
    return {
        "runId": run_id,
        "workerIds": body["workerIds"],
        "workload": body["task"],
        "coordinatorDeviceId": body["coordinatorDeviceId"],
        "backupPolicy": body["backupPolicy"],
        **{
            key: body[key]
            for key in (
                "candidatesPerGeneration",
                "maxGenerations",
                "alpha",
                "sigma",
                "decodeEngine",
                "schedulerPolicy",
                "syncMode",
            )
        },
    }


def test_blocked_head_does_not_stall_disjoint_jobs(lab):
    _, store, runtime, _ = lab
    off, _ = pair(lab, "off")
    a, ah = pair(lab, "a")
    b, bh = pair(lab, "b")
    enable(lab, a, ah)
    enable(lab, b, bh)
    first = queued(lab, off)
    second = queued(lab, a)
    third = queued(lab, b)
    store.dispatch_once()
    assert store.get(first)["status"] == "QUEUED"
    assert store.get(second)["status"] == store.get(third)["status"] == "STARTING"
    assert {r["runId"] for r in runtime.runs()} == {second, third}


def test_native_and_wsl_aliases_cannot_allocate_same_physical_gpu(lab):
    _, store, runtime, _ = lab
    a, ah = pair(lab, "native")
    b, bh = pair(lab, "wsl")
    same_gpu(lab, b, bh, a)
    enable(lab, a, ah)
    enable(lab, b, bh)
    first = queued(lab, a)
    second = queued(lab, b)
    store.dispatch_once()
    assert store.get(first)["status"] == "STARTING"
    assert store.get(second)["status"] == "QUEUED"
    assert "GPU release" in store.get(second)["waitingReason"]
    assert all(d["allocatedTo"] == first for d in runtime.devices())
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM physical_reservations").fetchone()[0] == 1
        # A lost heartbeat never frees GPU ownership.
        db.execute("UPDATE devices SET seen=? WHERE id=?", (time.time() - 60, a["deviceId"]))
    store.dispatch_once()
    assert len(runtime.runs()) == 1
    assert runtime.reservations()


def test_coordinator_and_worker_share_one_physical_reservation(lab):
    _, store, _, _ = lab
    d, h = pair(lab)
    enable(lab, d, h)
    queued(lab, d)
    store.dispatch_once()
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM physical_reservations").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM device_reservations").fetchone()[0] == 1


def test_concurrent_reservation_is_atomic_across_store_connections(lab):
    _, store, runtime, _ = lab
    a, ah = pair(lab, "native")
    b, bh = pair(lab, "wsl")
    same_gpu(lab, b, bh, a)
    enable(lab, a, ah)
    enable(lab, b, bh)
    first = queued(lab, a)
    second = queued(lab, b)
    other_runtime = AgentRuntime()
    other_store = Store(store.path, {}, other_runtime)

    def reserve(pair):
        candidate, run_id = pair
        try:
            candidate.submit(config(store, run_id))
            return "reserved"
        except ConnectionError:
            return "blocked"

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(reserve, [(runtime, first), (other_runtime, second)]))
    assert sorted(results) == ["blocked", "reserved"]
    assert len(runtime.runs()) == 1


def test_missing_profile_waits_and_reserved_uuid_cannot_change(lab):
    client, store, runtime, _ = lab
    d, h = pair(lab)
    profile = runtime.devices()[0]["selfTest"]
    legacy = {**profile, "gpuUUID": None}
    boot(client, h, "boot-1", selfTest=legacy)
    enable(lab, d, h)
    run_id = queued(lab, d)
    store.dispatch_once()
    assert store.get(run_id)["status"] == "QUEUED"
    assert "self-test" in store.get(run_id)["waitingReason"]
    boot(client, h, "boot-1", contribution=True, selfTest=profile)
    store.dispatch_once()
    assert store.get(run_id)["status"] == "STARTING"
    response = client.post("/api/v1/device/poll", headers=h, json={"bootId": "boot-1", "selfTest": legacy})
    assert response.status_code == 409


def test_monitoring_failure_on_one_job_does_not_hide_another(lab, monkeypatch):
    _, store, runtime, _ = lab
    a, ah = pair(lab, "a")
    b, bh = pair(lab, "b")
    enable(lab, a, ah)
    enable(lab, b, bh)
    first = queued(lab, a)
    second = queued(lab, b)
    store.dispatch_once()
    snapshot = runtime.snapshot
    observed = []

    def unreliable(run_id):
        observed.append(run_id)
        if run_id == first:
            raise ConnectionError("Temporary outage")
        return snapshot(run_id)

    monkeypatch.setattr(runtime, "snapshot", unreliable)
    store.dispatch_once()
    assert second in observed
    assert store.last_error == "ConnectionError"
