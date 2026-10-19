#!/usr/bin/env python3
"""A throwaway CPU-only lab for browser/Electron checks: temporary state, agent mode, fake installers.

    serve-test-lab.py --web <built frontend> --port 18080

Accounts: admin / test-admin-pass (platform administrator), participant / test-user-pass. Like the live lab it runs in
agent mode; two devices are paired the way a Worker pairs (code, enrollment, approval) and show as offline: '5070ti'
(coordinator) and '3060' (worker). It never touches the real lab, its configuration or its installers. Stop it with Ctrl-C or SIGTERM; its state directory is deleted on exit.
"""

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]

from fastapi.testclient import TestClient  # noqa: E402
import uvicorn  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.devices import AgentRuntime  # noqa: E402

USERS = {"admin": "test-admin-pass", "participant": "test-user-pass"}


def pair_devices(app):
    """Pair, enroll and approve two Linux devices through the lab's own routes (no lifespan: requests only)."""
    import uuid

    client = TestClient(app)
    token = client.post("/api/v1/auth/login", json={"username": "admin", "password": USERS["admin"]}).json()[
        "accessToken"
    ]
    admin = {"Authorization": "Bearer " + token, "X-Workspace-Id": "lab"}
    for alias, gpu, vram, coordinator in (
        ("5070ti", "NVIDIA GeForce RTX 5070 Ti", 16303, True),
        ("3060", "NVIDIA GeForce RTX 3060", 12288, False),
    ):
        code = client.post("/api/v1/devices/pairing-codes", headers=admin).json()["code"]
        enrolled = client.post(
            "/api/v1/device/enroll",
            json={
                "code": code,
                "workerId": alias,
                "displayName": alias,
                "computeUrl": "http://100.64.0.1:8769",
                "selfTest": {
                    "passed": True,
                    "coordinator": coordinator,
                    "gpuName": gpu,
                    "vramTotalMb": vram,
                    "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
                    "gpuUUID": "GPU-" + str(uuid.uuid5(uuid.NAMESPACE_DNS, alias)),
                },
            },
        )
        enrolled.raise_for_status()
        approved = client.patch(
            "/api/v1/platform/devices/" + enrolled.json()["deviceId"],
            json={"approved": True, "workspaceId": "lab"},
            headers=admin,
        )
        approved.raise_for_status()
    client.post("/api/v1/auth/logout", headers=admin)


def load_run(store, recorded):
    """Insert a recorded run (as exported from a real lab) as a finished experiment of the lab workspace, owned by the administrator."""
    import uuid

    with store.db() as db:
        admin = next(
            user
            for user in db.execute("SELECT id, profile FROM users")
            if json.loads(user[1]).get("username") == "admin"
        )
    run_id = uuid.uuid4().hex
    body = {**recorded["body"], "experimentId": run_id, "ownerUserId": admin[0], "workspaceId": "lab"}
    snapshot = json.loads(json.dumps(recorded["snapshot"]))
    for group in ("generations", "candidates", "attempts", "artifacts"):
        for item in snapshot.get(group, []):
            for key in ("experimentId", "generationId", "candidateId", "attemptId"):
                if key in item and isinstance(item[key], str):
                    item[key] = item[key].replace(recorded["body"]["experimentId"], run_id)
    with store.db() as db:
        db.execute(
            "INSERT INTO experiments VALUES (?,?,?,?)", (run_id, admin[0], json.dumps(body), json.dumps(snapshot))
        )
    return run_id


def start_simulation(store, recording):
    """Insert the recording as a RUNNING experiment and keep rewriting its stored snapshot as time passes."""
    import threading
    import time

    sys.path.insert(0, str(ROOT / "scripts"))
    from lab_replay import reveal
    from lab_replay import shift

    # The recording is days old: move its times so that the run starts now and "now" on the server means the same thing.
    began = time.time()
    first = recording["snapshot"]["state"]["startedAt"]
    recording = shift(recording, began - first + 1.0)
    first = recording["snapshot"]["state"]["startedAt"]
    run_id = load_run(
        store, {**recording, "body": {**recording["body"], "name": recording["body"]["name"] + " (live simulation)"}}
    )
    with store.db() as db:
        identity = json.loads(db.execute("SELECT body FROM experiments WHERE id=?", (run_id,)).fetchone()[0])
    full_rename = {recording["body"]["experimentId"]: run_id}

    def rename(value):
        text = json.dumps(value)
        for old, new in full_rename.items():
            text = text.replace(old, new)
        return json.loads(text)

    def loop():
        while True:
            body, snapshot = reveal(recording, time.time())
            body, snapshot = rename(body), rename(snapshot)
            body.update(
                experimentId=run_id, ownerUserId=identity["ownerUserId"], workspaceId="lab", name=identity["name"]
            )
            with store.db() as db:
                db.execute(
                    "UPDATE experiments SET body=?, snapshot=? WHERE id=?",
                    (json.dumps(body), json.dumps(snapshot), run_id),
                )
            if body["status"] == "COMPLETED":
                return
            time.sleep(0.4)

    threading.Thread(target=loop, daemon=True).start()
    print("simulating live run", run_id, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--simulate-live", type=Path, help="a recorded run to reveal over time as if it were running now"
    )
    parser.add_argument(
        "--seed-run",
        type=Path,
        action="append",
        default=[],
        help="a recorded run ({body, snapshot} JSON) to load as a finished experiment",
    )
    args = parser.parse_args()
    state = Path(tempfile.mkdtemp(prefix="test-lab-"))
    try:
        downloads = state / "downloads"
        downloads.mkdir()
        installers = [
            {
                "platform": "windows",
                "name": "HeteroES-Worker-test-Windows.exe",
                "url": "/downloads/HeteroES-Worker-test-Windows.exe",
            },
            {
                "platform": "linux",
                "name": "HeteroES-Worker-test-Linux.tar.gz",
                "url": "/downloads/HeteroES-Worker-test-Linux.tar.gz",
            },
        ]
        for item in installers:
            (downloads / item["name"]).write_bytes(b"not a real installer")
        (downloads / "manifest.json").write_text(
            json.dumps({"version": "0.1.0", "build": "test", "installers": installers, "serverInstallers": []})
        )
        app = create_app(
            state / "product.sqlite",
            USERS,
            AgentRuntime(),
            dispatch=False,
            web_directory=args.web.resolve(),
            downloads_directory=downloads,
        )
        pair_devices(app)
        for recorded in args.seed_run:
            load_run(app.state.store, json.loads(recorded.read_text()))
        if args.simulate_live:
            start_simulation(app.state.store, json.loads(args.simulate_live.read_text()))
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        shutil.rmtree(state, ignore_errors=True)


if __name__ == "__main__":
    main()
