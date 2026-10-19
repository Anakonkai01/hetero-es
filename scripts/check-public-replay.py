#!/usr/bin/env python3
"""Real GPU acceptance: a worker that reaches the coordinator only through the lab's PUBLIC address.

The device's advertised private address is changed to a port nothing listens on, so the worker agent cannot use
the private route and must fall back to publicComputeUrl (Cloudflare tunnel -> Caddy entry -> coordinator) with
--no-bulk. A short experiment then runs on the GPU. The evidence file records what the worker's own log shows:
public coordinator address, replay events, and that no whole-weights download (sync) happened.

Runs on the lab host with the lab's private configuration. Needs --gpu and HETEROES_GPU_ACCEPTANCE=1.
The lab must be idle (no reservations, empty queue, the device OFF and its agent stopped). Everything it
changes (the device address, contribution, the agent process) is restored; a dispatch hold is released
because the experiment needs it, and stays released.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
import urllib.error
import urllib.request

TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}


class Lab:
    def __init__(self, base, username, password):
        self.base, self.headers = base.rstrip("/"), {"Content-Type": "application/json", "X-Workspace-Id": "lab"}
        token = self.call("POST", "/auth/login", {"username": username, "password": password}, auth=False)[
            "accessToken"
        ]
        self.headers["Authorization"] = "Bearer " + token

    def call(self, method, path, body=None, auth=True):
        headers = self.headers if auth else {"Content-Type": "application/json"}
        request = urllib.request.Request(
            self.base + "/api/v1" + path,
            method=method,
            headers=headers,
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as reply:
                return json.load(reply) if reply.status != 204 else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{method} {path}: HTTP {error.code} {error.read()[:200]!r}") from None


def wait(check, seconds, what, step=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(step)
    raise TimeoutError(what)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--private", type=Path, default=Path.home() / ".config/heteroes-m2")
    parser.add_argument(
        "--agent-config", type=Path, default=Path.home() / ".config/heteroes-private/ui-local-agent/config.json"
    )
    parser.add_argument("--runtime-src", type=Path, required=True, help="Track A src directory")
    parser.add_argument("--python", required=True, help="interpreter with the GPU runtime (heteroes-match)")
    parser.add_argument("--output", type=Path, required=True, help="evidence JSON (never overwritten)")
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--candidates", type=int, default=4)
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    if not (args.gpu and os.environ.get("HETEROES_GPU_ACCEPTANCE") == "1"):
        sys.exit("GPU acceptance needs --gpu and HETEROES_GPU_ACCEPTANCE=1")
    if args.output.exists():
        sys.exit("Existing evidence is never overwritten")

    config = json.loads((args.private / "config.json").read_text())
    credentials = json.loads((args.private / "credentials.json").read_text())
    agent_config = json.loads(args.agent_config.read_text())
    state = Path(agent_config["stateDirectory"])
    public = config.get("publicComputeUrl")
    assert public and public.startswith("https://"), "the lab has no public compute address"
    original = urlsplit(agent_config["computeUrl"])
    assert config["privateComputeUrl"] == agent_config["computeUrl"], "the public entry must point at this coordinator"
    dead = f"{original.scheme}://{original.hostname}:{original.port + 1}"
    with socket.socket() as sock:
        sock.settimeout(0.5)
        assert sock.connect_ex((original.hostname, original.port + 1)) != 0, "the stand-in private port is in use"

    lab = Lab(config["apiUrl"], "admin", credentials["users"]["admin"])
    held = lab.call("GET", "/platform/operations")
    assert not held["reservations"] and not held["queueCount"], (
        "the lab must be idle: no reservations and an empty queue"
    )
    device = next(d for d in lab.call("GET", "/platform/devices") if d["workerId"] == agent_config["workerId"])
    assert not device["contributionEnabled"] and device["connectionStatus"] == "OFFLINE", (
        "stop the device and its agent first"
    )
    device_id = device["deviceId"]
    restore = {
        "computeUrl": device["computeUrl"],
        "bulkUrl": device["bulkUrl"] if device["bulkUrl"] != device["computeUrl"] else None,
    }
    evidence = {
        "format": 1,
        "startedAt": time.time(),
        "publicComputeUrl": public,
        "advertisedPrivateUrl": dead,
        "generations": args.generations,
        "candidates": args.candidates,
        "gpuName": agent_config["selfTest"].get("gpuName"),
    }
    agent = None
    log = open(args.output.with_suffix(".agent.log"), "xb")
    try:
        lab.call("PATCH", f"/devices/{device_id}/endpoints", {"computeUrl": dead})
        env = dict(os.environ, PYTHONPATH=str(args.runtime_src), PYTHONNOUSERSITE="1")
        agent = subprocess.Popen(
            [args.python, "-m", "heteroes.product.agent", "run", "--config", str(args.agent_config)],
            env=env,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        wait(
            lambda: (
                next(d for d in lab.call("GET", "/platform/devices") if d["deviceId"] == device_id)["connectionStatus"]
                == "ONLINE"
            ),
            90,
            "the agent did not come online",
        )
        boot = json.loads((state / "boot.json").read_text())["bootId"]
        lab.call("POST", f"/devices/{device_id}/contribution", {"enabled": True, "bootId": boot})
        wait(
            lambda: next(d for d in lab.call("GET", "/platform/devices") if d["deviceId"] == device_id)[
                "contributionEnabled"
            ],
            60,
            "contribution did not turn ON",
        )
        if held["dispatchHeld"]:
            lab.call("POST", "/platform/maintenance/resume", {"workerConfigurationConfirmed": True})
        run = lab.call(
            "POST",
            "/experiments",
            {
                "name": "public-route replay-only acceptance",
                "modelName": "Qwen/Qwen2.5-0.5B-Instruct",
                "schedulerPolicy": "greedy",
                "syncMode": "synchronous",
                "workerIds": [agent_config["workerId"]],
                "task": "arith16",
                "maxGenerations": args.generations,
                "candidatesPerGeneration": args.candidates,
                "alpha": 0.001,
                "sigma": 0.001,
                "decodeEngine": "hf_generate",
                "coordinatorDeviceId": device_id,
            },
        )
        run_id = run["experimentId"]
        lab.call("POST", f"/experiments/{run_id}/submit", {})
        seen = []

        def finished():
            body = lab.call("GET", f"/experiments/{run_id}")
            if not seen or seen[-1] != body["status"]:
                seen.append(body["status"])
                print(
                    time.strftime("%H:%M:%S"),
                    body["status"],
                    "generations",
                    body.get("completedGenerations"),
                    flush=True,
                )
            return body if body["status"] in TERMINAL else None

        body = wait(finished, 1500, "the experiment did not finish", step=3)
        evidence.update(
            experimentId=run_id,
            statuses=seen,
            finalStatus=body["status"],
            completedGenerations=body.get("completedGenerations"),
            finalModelVersion=body.get("modelVersion"),
            failureReason=body.get("failureReason"),
        )
        logs = sorted((state / "workers").glob("*/r*/events.jsonl"), key=lambda p: p.stat().st_mtime)
        events = [json.loads(line) for line in logs[-1].read_text().splitlines() if line.strip()] if logs else []
        start = next((e for e in events if e.get("event") == "worker_start"), {})
        evidence["worker"] = {
            "log": str(logs[-1]) if logs else None,
            "coordinatorUrl": start.get("args", {}).get("coordinator_url"),
            "noBulk": start.get("args", {}).get("no_bulk"),
            "bulkUrl": start.get("args", {}).get("bulk_url"),
            "replayMaxChain": start.get("args", {}).get("replay_max_chain"),
            "replays": [
                {k: e.get(k) for k in ("steps", "verified", "apply_seconds")}
                for e in events
                if e.get("event") == "replay"
            ],
            "syncs": sum(e.get("event") == "sync" for e in events),
            "committedSteps": sum(e.get("event") == "step" and e.get("kind") == "COMMITTED" for e in events),
            "exit": next((e.get("reason") for e in events if e.get("event") == "exit"), None),
        }
        parents = [
            g["modelVersion"]
            for g in sorted(
                lab.call("GET", f"/experiments/{run_id}/generations"),
                key=lambda g: g["generationId"].rsplit(".g", 1)[1].zfill(6),
            )
        ]
        evidence["parentChanges"] = sum(a != b for a, b in zip(parents, parents[1:]))
        w = evidence["worker"]
        evidence["checks"] = {
            "experimentCompleted": body["status"] == "COMPLETED"
            and body.get("completedGenerations") == args.generations,
            "workerUsedThePublicAddress": w["coordinatorUrl"] == public,
            "workerHadNoBulkRoute": w["noBulk"] is True and not w["bulkUrl"],
            # An update whose rewards are all equal is a no-op, so the parent weights change only some generations:
            # the worker needs exactly one verified replay per change.
            "workerCaughtUpByReplay": len(w["replays"]) == evidence["parentChanges"]
            and all(r["verified"] for r in w["replays"]),
            "noWholeWeightsDownload": w["syncs"] == 0,
            "candidatesCommittedByTheWorker": w["committedSteps"] >= args.generations * args.candidates,
        }
    finally:
        try:
            boot_now = json.loads((state / "boot.json").read_text())["bootId"]
            lab.call("POST", f"/devices/{device_id}/contribution", {"enabled": False, "bootId": boot_now})

            def drained():
                ops = lab.call("GET", "/platform/operations")
                dev = next(d for d in lab.call("GET", "/platform/devices") if d["deviceId"] == device_id)
                return not ops["reservations"] and not dev["allocatedTo"] and not dev["contributionEnabled"]

            wait(drained, 180, "the device did not drain")
            evidence["drained"] = True
        except Exception as error:
            evidence["drained"] = f"FAILED: {type(error).__name__}: {error}"
        # The address is restored whatever happened above; the server accepts it once the agent reports every process stopped.
        for attempt in range(12):
            try:
                lab.call("PATCH", f"/devices/{device_id}/endpoints", {k: v for k, v in restore.items() if v})
                evidence["restored"] = True
                break
            except Exception as error:
                evidence["restored"] = f"FAILED: {type(error).__name__}: {error}"
                time.sleep(10)
        if agent and agent.poll() is None:
            agent.send_signal(signal.SIGTERM)
            try:
                agent.wait(timeout=60)
            except subprocess.TimeoutExpired:
                evidence["agentStopped"] = "did not stop within 60 s; left running"
        log.close()
        evidence["finishedAt"] = time.time()
        args.output.write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps({k: evidence.get(k) for k in ("finalStatus", "checks", "restored")}, indent=2))


if __name__ == "__main__":
    main()
