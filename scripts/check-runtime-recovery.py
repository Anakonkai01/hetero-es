#!/usr/bin/env python3
"""Controlled GPU acceptance: coordinator SIGKILL, one recovery, FIFO and offline fallback.

Run only against the private local deployment. Signals only the tracked coordinator
after checking its /proc birth time. Runtime logs and checkpoints remain untouched.
"""
import json
import os
from pathlib import Path
import signal
import sqlite3
import time
import urllib.error
import urllib.request

PRIVATE = Path(os.environ.get("HETEROES_PRIVATE_CONFIG", str(Path.home() / ".config/heteroes-integration")))
config = json.loads((PRIVATE / "config.json").read_text())
credentials = json.loads((PRIVATE / "credentials.json").read_text())
base = "http://127.0.0.1:8000/api/v1"
output = Path(config["productStateDirectory"]) / "recovery-evidence.json"


def call(route, body=None, token=None, method=None):
    headers = {"Content-Type": "application/json", "X-Workspace-Id": "lab"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + route, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response) if response.status != 204 else None


def wait(check, seconds=600):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.5)
    raise TimeoutError("runtime acceptance timed out")


token = call("/auth/login", {"username": "admin", "password": credentials["users"]["admin"]})["accessToken"]
assert not any(run["status"] in ("STARTING", "RUNNING", "CANCELLING", "RECOVERING", "DRAINING", "QUEUED") for run in call("/experiments", token=token))


def create(name, workers, generations, candidates):
    run = call("/experiments", {"name": name, "modelName": "Qwen/Qwen2.5-0.5B-Instruct", "schedulerPolicy": "greedy",
        "syncMode": "synchronous", "workerIds": workers, "task": "arith16", "maxGenerations": generations,
        "candidatesPerGeneration": candidates, "alpha": .001, "sigma": .001, "decodeEngine": "hf_generate"}, token)
    call("/experiments/" + run["experimentId"] + "/submit", {}, token)
    return run["experimentId"]


def get(run_id):
    return call("/experiments/" + run_id, token=token)


def terminal(run_id):
    run = get(run_id)
    return run if run["status"] in ("COMPLETED", "FAILED", "CANCELLED") else None


started = time.time()
run_id = create("Coordinator recovery acceptance", ["5070ti"], 3, 8)
queued_id = create("FIFO and remote-worker fallback", ["5070ti", "3060"], 1, 2)
cancelled_id = create("Queued cancellation acceptance", ["5070ti"], 1, 2)
assert call("/experiments/" + cancelled_id + "/cancel", {}, token)["status"] == "CANCELLED"
root = Path(config["stateDirectory"]) / run_id
wait(lambda: get(run_id).get("completedGenerations", 0) >= 1)
assert get(queued_id)["status"] == "QUEUED"
record = json.loads((root / "process.json").read_text())
fields = Path(f"/proc/{record['pid']}/stat").read_text().rsplit(")", 1)[1].split()
assert fields[19] == record["birth"]
os.kill(record["pid"], signal.SIGKILL)
print("Injected one tracked coordinator failure after the first complete generation", flush=True)
result = wait(lambda: terminal(run_id))
assert result["status"] == "COMPLETED", result
state = json.loads((root / "state.json").read_text())
assert state["recoveryCount"] == 1
assert result["completedGenerations"] == 3
fallback = wait(lambda: terminal(queued_id))
assert fallback["status"] == "COMPLETED", fallback
fallback_state = json.loads((Path(config["stateDirectory"]) / queued_id / "state.json").read_text())
assert not (Path(config["stateDirectory"]) / cancelled_id).exists()
artifacts = call("/artifacts", token=token)
checkpoint = next(item for item in artifacts if item["experimentId"] == run_id and item["type"] == "CHECKPOINT")
request = urllib.request.Request(base + f"/artifacts/{checkpoint['artifactId']}/download", headers={"Authorization": "Bearer " + token, "X-Workspace-Id": "lab"})
import hashlib
digest = hashlib.sha256()
with urllib.request.urlopen(request, timeout=120) as response:
    while block := response.read(1024 * 1024):
        digest.update(block)
assert digest.hexdigest() == result["modelVersion"]
evidence = {"recoveredRunId": run_id, "queuedRunId": queued_id, "cancelledQueuedRunId": cancelled_id,
    "recoveryCount": state["recoveryCount"], "finalCheckpointSha256": digest.hexdigest(),
    "fallbackWorkerStates": fallback_state["workerStates"], "wallSeconds": time.time() - started}
with sqlite3.connect(f"file:{Path(config['stateDirectory']) / queued_id / 'ledger.sqlite'}?mode=ro", uri=True) as db:
    counts = dict(db.execute("SELECT a.worker_id,count(*) FROM result r JOIN attempt a USING(candidate_id,attempt_number) GROUP BY a.worker_id"))
evidence.update(acceptedResultsByWorker=counts,
                requiredTwoGpuAcceptance=set(counts) == {"5070ti", "3060"} and all(counts.values()))
output.write_text(json.dumps(evidence, indent=2))
print("PASS one automatic recovery, 3 complete generations, FIFO, queued cancellation and checkpoint download hash", flush=True)
print(f"Evidence: {output}", flush=True)
