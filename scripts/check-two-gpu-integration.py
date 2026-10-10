#!/usr/bin/env python3
"""Run the pinned N=8/G=3 recipe and prove accepted results from both required GPUs."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import urllib.request

private = Path(os.environ.get("HETEROES_PRIVATE_CONFIG", str(Path.home() / ".config/heteroes-integration")))
config = json.loads((private / "config.json").read_text())
credentials = json.loads((private / "credentials.json").read_text())
base = f"http://127.0.0.1:{config.get('backendPort',8000)}/api/v1"
token = None


def call(route, body=None):
    headers = {"Content-Type": "application/json", "X-Workspace-Id": "lab"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + route, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


token = call("/auth/login", {"username": "admin", "password": credentials["users"]["admin"]})["accessToken"]
assert not any(run["status"] in ("STARTING", "RUNNING", "CANCELLING", "RECOVERING", "DRAINING", "QUEUED")
               for run in call("/experiments")), "Acceptance requires an idle queue and pool"
started = time.time()
run = call("/experiments", {"name": "Required 5070 Ti + Quang 3060 acceptance", "modelName": "Qwen/Qwen2.5-0.5B-Instruct",
    "schedulerPolicy": "greedy", "syncMode": "synchronous", "workerIds": ["5070ti", "3060"], "task": "arith16",
    "maxGenerations": 3, "candidatesPerGeneration": 8, "alpha": .001, "sigma": .001, "decodeEngine": "hf_generate"})
run_id = run["experimentId"]
call(f"/experiments/{run_id}/submit", {})
print(f"Started required two-GPU run {run_id}", flush=True)
deadline = time.monotonic() + 1800
while True:
    result = call(f"/experiments/{run_id}")
    if result["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
        break
    if time.monotonic() > deadline:
        call(f"/experiments/{run_id}/cancel", {})
        raise TimeoutError("Requested safe cancellation after the acceptance deadline")
    time.sleep(1)
assert result["status"] == "COMPLETED", result
assert result["completedGenerations"] == 3, result
root = Path(config["stateDirectory"]) / run_id
with sqlite3.connect(f"file:{root / 'ledger.sqlite'}?mode=ro", uri=True) as db:
    counts = dict(db.execute("SELECT a.worker_id,count(*) FROM result r JOIN attempt a USING(candidate_id,attempt_number) GROUP BY a.worker_id"))
    updates = db.execute("SELECT count(*) FROM generation_update WHERE applied_at IS NOT NULL").fetchone()[0]
assert set(counts) == {"5070ti", "3060"} and all(counts.values()), counts
assert sum(counts.values()) == 24 and updates == 3, (counts, updates)
state = json.loads((root / "state.json").read_text())
assert all(state["workerStates"][worker]["ready"] and state["workerStates"][worker]["confirmed"]
           and not state["workerStates"][worker]["alive"] for worker in counts)
artifact = next(item for item in call("/artifacts") if item["experimentId"] == run_id and item["type"] == "CHECKPOINT")
request = urllib.request.Request(base + f"/artifacts/{artifact['artifactId']}/download",
    headers={"Authorization": "Bearer " + token, "X-Workspace-Id": "lab"})
digest = hashlib.sha256()
with urllib.request.urlopen(request, timeout=120) as response:
    while block := response.read(1024 * 1024):
        digest.update(block)
assert digest.hexdigest() == result["modelVersion"]
evidence = {"runId": run_id, "status": result["status"], "acceptedResultsByWorker": counts,
    "publishedGenerations": updates, "checkpointSha256": digest.hexdigest(), "workerStates": state["workerStates"],
    "wallSeconds": time.time() - started, "requiredTwoGpuAcceptance": True}
output = Path(config["productStateDirectory"]) / "two-gpu-evidence.json"
output.write_text(json.dumps(evidence, indent=2))
print(f"PASS 3 published generations, 24 accepted results across both GPUs, checkpoint hash, confirmed shutdown: {output}", flush=True)
