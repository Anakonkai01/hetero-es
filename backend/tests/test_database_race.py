"""Separate product processes must not grant the same device/GPU to two live assignments."""

import json
import multiprocessing
import os
from queue import Empty

from backend.services.devices import AgentRuntime
from backend.services.store import Store
from labkit import enable, pair, queued


def _submit_in_process(path, dialect, schema, configuration, barrier, outcomes):
    options = {}
    if dialect == "postgresql":
        options = {
            "database_url": os.environ["HETEROES_TEST_DATABASE_URL"],
            "database_connect_args": {"options": "-csearch_path=" + schema + " -clock_timeout=10000"},
        }
    runtime = AgentRuntime()
    store = None
    try:
        store = Store(path, {}, runtime, **options)
        barrier.wait(20)
        try:
            runtime.submit(configuration)
            outcome = "won"
        except ConnectionError:
            outcome = "reserved"
        outcomes.put((outcome, store.database.dialect))
    except BaseException as error:
        # Never serialize a driver error message or connection configuration into the test report.
        outcomes.put(("unexpected:" + type(error).__name__, dialect))
    finally:
        if store is not None:
            store.close()


def test_two_processes_competing_for_a_device_grant_exactly_one_assignment(lab):
    _, store, _, _ = lab
    device, authentication = pair(lab, "race-device")
    enable(lab, device, authentication)
    runs = [queued(lab, device), queued(lab, device)]
    dialect = store.database.dialect
    with store.db() as db:
        schema = db.execute("SELECT current_schema()").fetchone()[0] if dialect == "postgresql" else None
    configurations = [
        {
            "runId": run,
            "workerIds": [device["workerId"]],
            "coordinatorDeviceId": device["deviceId"],
            "backupPolicy": {"interval": 1, "retain": 3},
        }
        for run in runs
    ]
    context = multiprocessing.get_context("spawn")
    barrier, outcomes = context.Barrier(3), context.Queue()
    processes = [
        context.Process(target=_submit_in_process, args=(store.path, dialect, schema, config, barrier, outcomes))
        for config in configurations
    ]
    try:
        for process in processes:
            process.start()
        barrier.wait(20)
        result = [outcomes.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(20)
        assert all(process.exitcode == 0 for process in processes)
        assert sorted(result) == [("reserved", dialect), ("won", dialect)]
        with store.db() as db:
            assignment = db.execute("SELECT id,run_id,body FROM assignments WHERE released=0").fetchall()
            assert len(assignment) == 1 and assignment[0]["run_id"] in runs
            assert json.loads(assignment[0]["body"])["deviceIds"] == [device["deviceId"]]
            assert [tuple(row) for row in db.execute("SELECT device_id,assignment_id FROM device_reservations")] == [
                (device["deviceId"], assignment[0]["id"])
            ]
            assert (
                db.execute(
                    "SELECT count(*) FROM physical_reservations WHERE assignment_id=:p0", (assignment[0]["id"],)
                ).fetchone()[0]
                == 1
            )
            assert db.execute("SELECT count(*) FROM audit WHERE action='ASSIGNMENT_CREATED'").fetchone()[0] == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(5)
        outcomes.close()
        outcomes.join_thread()
