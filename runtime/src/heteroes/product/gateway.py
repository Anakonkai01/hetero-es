"""Loopback-only runtime control API and durable, single-run process supervisor."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time

from .files import events, read_json, write_json
from .remote import alive, identity
from .storage import data_root, checked_directory

TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}
QUIESCENT = TERMINAL | {'PAUSED'}
ROOT = Path(__file__).resolve().parents[3]
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp is not None else None


def capabilities(workers):
    return {"controlApiVersion": 1, "modelId": MODEL, "modelRevision": REVISION,
            "workloads": ["arith16", "cot_l3_q32", "cot_l3_q64", "cot_l1_q128"],
            "schedulerPolicies": ["greedy"], "syncModes": ["synchronous"],
            "workerIds": list(workers), "maxRunSeconds": None,
            "unsupported": ["pause", "resume", "change-workers", "model-upload", "dataset-upload", "asynchronous"]}


def validate(config, workers):
    if not re.fullmatch(r"[a-f0-9]{32}", config.get("runId", "")):
        raise ValueError("runId must be a UUID hex identifier")
    for key, low, high in (("maxGenerations", 1, 1000), ("candidatesPerGeneration", 2, 256)):
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}")
    for key in ("alpha", "sigma"):
        value = config.get(key)
        if type(value) not in (int, float) or not 0 < value <= 1:
            raise ValueError(f"{key} must be finite and between 0 and 1")
    if config.get("workload") not in capabilities(workers)["workloads"] and not (config.get('recipeVersion')==2 and config.get('workload')=='text_math_v2'):
        raise ValueError("unsupported workload")
    if config.get("decodeEngine") not in ("hf_generate", "hf_compact"):
        raise ValueError("unsupported decoder")
    selected = config.get("workerIds")
    if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected) or not set(selected) <= set(workers):
        raise ValueError("select unique configured worker IDs")
    if config.get("schedulerPolicy") != "greedy" or config.get("syncMode") != "synchronous":
        raise ValueError("only the greedy synchronous policy is configured")


class Manager:
    def __init__(self, config, token):
        self.config, self.token = config, token
        self.root = Path(config["stateDirectory"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workers = {worker["id"]: worker for worker in config["workers"]}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.processes = {}  # reap owned children rather than leaking zombie processes
        self.cache, self.cache_at = [], 0
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def directory(self, run_id):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("invalid run ID")
        return self.root / run_id

    def state(self, root):
        return read_json(root / "state.json", {})

    def save(self, root, **changes):
        write_json(root / "state.json", {**self.state(root), **changes, "updatedAt": time.time()})

    def log(self, root, event, **fields):
        with open(root / "lifecycle.jsonl", "a") as output:
            output.write(json.dumps({"event": event, "t": time.time(), **fields}) + "\n")

    def submit(self, body):
        validate(body, self.workers)
        root = self.directory(body["runId"])
        with self.lock:
            if read_json(self.root/'maintenance.json'):
                raise RuntimeError('Runtime is held for maintenance')
            old = read_json(root / "config.json")
            if old:
                if any(old.get(key) != value for key, value in body.items()):
                    raise ValueError("run ID already belongs to a different configuration")
                return self.state(root)
            quarantined = read_json(self.root / "quarantine.json", {})
            if set(body["workerIds"]) & set(quarantined):
                raise ValueError("Selected worker is quarantined after a restore mismatch; administrator investigation required")
            pending = [path for path in self.root.iterdir() if path.is_dir() and self.state(path).get("status") not in QUIESCENT]
            if pending:
                raise RuntimeError("another run still owns the GPU pool")
            root.mkdir(mode=0o700)
            if self.config.get('largeDataDirectory'):
                try:
                    large=checked_directory(self.config['largeDataDirectory'],self.config.get('storageVolumeUUID'))/'coordinators'/body['runId']
                    large.mkdir(parents=True,exist_ok=False,mode=0o700)
                    write_json(root/'large-data.json',{'directory':str(large),'volumeUUID':self.config.get('storageVolumeUUID')})
                except BaseException:
                    root.rmdir()
                    raise
            write_json(root / "config.json", {**body, "modelPath": self.config["modelPath"],
                                              "host": self.config["workerHost"], "port": self.config["workerPort"]})
            self.save(root, status="STARTING", recoveryCount=0, startedAt=time.time(), workerStates={})
            return self.state(root)

    def acquire_maintenance(self):
        from .backup import assert_idle
        import uuid
        with self.lock:
            assert_idle(self)
            old=read_json(self.root/'maintenance.json')
            if old:
                return old
            hold={'maintenanceId':uuid.uuid4().hex,'createdAt':time.time()}
            write_json(self.root/'maintenance.json',hold)
            return hold

    def check_maintenance(self,maintenance_id):
        hold=read_json(self.root/'maintenance.json')
        if not hold or not hmac.compare_digest(hold['maintenanceId'],maintenance_id):
            raise RuntimeError('A matching maintenance hold is required')

    def release_maintenance(self,maintenance_id):
        with self.lock:
            self.check_maintenance(maintenance_id)
            (self.root/'maintenance.json').unlink()
            return {'released':True}

    def create_backup(self,maintenance_id):
        from .backup import create_backup
        return create_backup(self,maintenance_id)

    def backup_path(self,backup_id):
        from .backup import backup_path
        return backup_path(self,backup_id)

    def discard_backup(self,backup_id):
        # This retires a completed transfer archive only, never run evidence.
        with self.lock:
            self.backup_path(backup_id).unlink()
            return {'discarded':True}

    def remote(self, worker, request):
        python, source = worker["python"], worker["source"]
        request = {**request, "directory": worker["stateDirectory"] + "/" + request.get("runId", "probe")}
        if worker.get("ssh"):
            command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", worker["ssh"],
                       f"env PYTHONPATH={shlex.quote(source)} {shlex.quote(python)} -m heteroes.product.remote"]
            environment = None
        else:
            command = [python, "-m", "heteroes.product.remote"]
            environment = dict(os.environ, PYTHONPATH=source)
        result = subprocess.run(command, input=json.dumps(request), capture_output=True, text=True,
                                timeout=25, env=environment)
        if result.returncode:
            raise RuntimeError("worker lifecycle command failed (see host connectivity/environment)")
        return json.loads(result.stdout)

    def probe(self, worker):
        try:
            value = self.remote(worker, {"action": "probe"})
            return {"workerId": worker["id"], "status": "ONLINE", "admissionStatus": "PENDING_VERIFICATION",
                    "admissionReason": "GPU reachable; recipe admission is checked when the run starts.",
                    "profile": {key: value[key] for key in ("gpuName", "vramTotalMb", "vramFreeMb")},
                    "temperatureC": value["temperatureC"], "utilizationPercent": value["utilizationPercent"],
                    "lastHeartbeatAt": iso(time.time())}
        except Exception:
            return {"workerId": worker["id"], "status": "OFFLINE", "admissionStatus": "INELIGIBLE",
                    "admissionReason": "Host, SSH or GPU probe unavailable.",
                    "profile": {"gpuName": worker["label"], "vramTotalMb": 0}}

    def registry(self):
        if time.time() - self.cache_at > 10:
            with ThreadPoolExecutor(max_workers=len(self.workers)) as executor:
                self.cache = list(executor.map(self.probe, self.workers.values()))
            self.cache_at = time.time()
        values = [dict(value) for value in self.cache]
        for path in self.root.iterdir():
            state = self.state(path) if path.is_dir() else {}
            if state.get("status") in QUIESCENT:
                continue
            selected = read_json(path / "config.json", {}).get("workerIds", [])
            for value in values:
                if value["workerId"] in selected:
                    value["allocatedTo"] = path.name
                    worker_state = state.get("workerStates", {}).get(value["workerId"], {})
                    if worker_state.get("ready") and worker_state.get("alive"):
                        value["admissionStatus"] = "ADMITTED"
                        value["admissionReason"] = "Executor passed the current run recipe self-tests."
        quarantined = read_json(self.root / "quarantine.json", {})
        for value in values:
            if value["workerId"] in quarantined:
                value.update(admissionStatus="INELIGIBLE", admissionReason="Quarantined after RESTORE_MISMATCH; administrator investigation required.")
        return values

    def launch(self, root):
        env = dict(os.environ, HETEROES_TOKEN=self.token, PYTHONPATH=str(ROOT / "src"))
        with open(root / "coordinator.log", "ab") as output:
            process = subprocess.Popen([self.config["python"], "-m", "heteroes.product.runner", str(root)],
                                        env=env, cwd=ROOT, stdout=output, stderr=output, start_new_session=True)
        self.processes[root.name] = process
        write_json(root / "process.json", {"pid": process.pid, "birth": identity(process.pid)})

    def start_worker(self, root, worker, recovery):
        config = read_json(root / "config.json")
        # Each restart has its own append-only worker evidence directory.
        remote_id = root.name + f"-r{recovery}"
        directory = worker["stateDirectory"] + "/" + remote_id
        argv = [worker["python"], worker["source"] + "/../scripts/run_worker.py",
                "--model-path", worker["modelPath"], "--coordinator-url", self.config["workerUrl"],
                "--worker-id", worker["id"], "--log", directory + "/events.jsonl",
                "--cache-dir", directory + "/cache", "--replay", "always", "--replay-verify-every", "1",
                "--give-up-after-seconds", "120", "--chunk", str(worker.get("chunk", 16))]
        return self.remote(worker, {"action": "start", "runId": remote_id, "argv": argv,
                                    "source": worker["source"], "token": self.token})

    def poll_workers(self, root, stop=False):
        state = self.state(root)
        recovery = state.get("recoveryCount", 0)
        result = dict(state.get("workerStates", {}))
        for worker_id, previous in list(result.items()):
            if previous.get("notStarted"):
                continue
            try:
                value = self.remote(self.workers[worker_id], {"action": "stop" if stop else "poll",
                                    "runId": root.name + f"-r{recovery}"})
                write_json(root / f"worker-{worker_id}-r{recovery}.json", value["events"])
                if any(item.get("failure") == "RESTORE_MISMATCH" or item.get("reason") == "quarantined" for item in value["events"]):
                    quarantined = read_json(self.root / "quarantine.json", {})
                    quarantined[worker_id] = {"runId": root.name, "t": time.time()}
                    write_json(self.root / "quarantine.json", quarantined)
                result[worker_id] = {"alive": value["alive"], "ready": value["ready"], "confirmed": True}
            except Exception:
                result[worker_id] = {**previous, "confirmed": False}
        self.save(root, workerStates=result)
        return all(value.get("notStarted") or (value.get("confirmed") and not value.get("alive")) for value in result.values())

    def tick(self, root):
        state = self.state(root)
        process_record = read_json(root / "process.json")
        if root.name in self.processes:
            self.processes[root.name].poll()
        running = alive(process_record)
        runner = read_json(root / "runner.json", {})
        if not process_record:
            self.launch(root)
            return
        if runner.get("status") == "PREPARING" and not state.get("workersLaunched"):
            result = {}
            for worker_id in read_json(root / "config.json")["workerIds"]:
                if worker_id in read_json(self.root / "quarantine.json", {}):
                    result[worker_id] = {"notStarted": True, "alive": False, "ready": False, "confirmed": True}
                    self.log(root, "worker_quarantined", worker_id=worker_id)
                    self.save(root, workerStates=result)
                    continue
                try:
                    self.remote(self.workers[worker_id], {"action": "probe"})
                except Exception:
                    result[worker_id] = {"notStarted": True, "alive": False, "ready": False, "confirmed": True}
                    self.log(root, "worker_unavailable", worker_id=worker_id)
                    self.save(root, workerStates=result)
                    continue
                # Persist unknown ownership BEFORE SSH, since a connection may die after launch.
                result[worker_id] = {"alive": True, "confirmed": False, "ready": False}
                self.save(root, workerStates=result)
                try:
                    value = self.start_worker(root, self.workers[worker_id], state.get("recoveryCount", 0))
                    result[worker_id] = {"alive": value["alive"], "confirmed": True, "ready": value["ready"]}
                except Exception:
                    self.log(root, "worker_start_unknown", worker_id=worker_id)
                self.save(root, workerStates=result)
            self.save(root, workersLaunched=True, preparingAt=time.time())
        state = self.state(root)
        if state.get("workersLaunched"):
            stopped = self.poll_workers(root)
        else:
            stopped = True
        state = self.state(root)
        if runner.get("status") == "PREPARING" and state.get("workersLaunched"):
            values = state["workerStates"].values()
            ready = any(value.get("ready") and value.get("alive") and value.get("confirmed") for value in values)
            settled = all(value.get("ready") or (value.get("confirmed") and not value.get("alive")) for value in values)
            if ready and (settled or time.time() - state["preparingAt"] > 180):
                for worker_id, value in state["workerStates"].items():
                    if not value.get("ready"):
                        self.log(root, "worker_unavailable", worker_id=worker_id)
                (root / "start.flag").touch()
            elif time.time() - state["preparingAt"] > 300:
                (root / "cancel.flag").touch()
                self.save(root, failureReason="No selected worker passed preparation")
        if runner.get("status") in QUIESCENT:
            if not stopped:
                stopped = self.poll_workers(root, stop=True)
            if stopped:
                (root / "workers-stopped.flag").touch()
                if not running:
                    self.save(root, status="FAILED" if state.get("failureReason") else runner["status"],
                              completedAt=time.time(), finalWeightsSha256=runner.get("final_weights_sha256"),
                              pauseCheckpoint=runner.get('pauseCheckpoint'),
                              failureReason=state.get("failureReason") or runner.get("failureReason"))
                    return
            self.save(root, status="CANCELLING" if runner["status"] == "CANCELLED" else
                      'PAUSING' if runner['status']=='PAUSED' else "DRAINING")
            return
        if not running:
            if not self.poll_workers(root, stop=True):
                self.save(root, status="RECOVERING", failureReason="Waiting for confirmed worker shutdown")
                return
            if state.get("recoveryCount", 0) >= 1:
                self.save(root, status="FAILED", failureReason="Coordinator failed twice", completedAt=time.time())
                return
            for name in ("runner.json", "process.json", "start.flag", "workers-stopped.flag"):
                (root / name).unlink(missing_ok=True)
            self.save(root, status="RECOVERING", recoveryCount=1, workersLaunched=False, workerStates={}, failureReason=None)
            self.log(root, "coordinator_recovery", recoveryCount=1)
            self.launch(root)
        else:
            self.save(root, status="CANCELLING" if (root / "cancel.flag").exists() else
                      'PAUSING' if (root/'pause.flag').exists() else
                      "RUNNING" if runner.get("status") == "RUNNING" else "STARTING")

    def loop(self):
        while not self.stop.wait(1):
            for root in self.root.iterdir():
                if not root.is_dir() or self.state(root).get("status") in QUIESCENT:
                    continue
                try:
                    with self.lock:
                        self.tick(root)
                except Exception as error:
                    self.log(root, "supervisor_error", error=f"{type(error).__name__}: {error}")

    def snapshot(self, run_id):
        root = self.directory(run_id)
        if not (root / "config.json").exists():
            raise FileNotFoundError("run not found")
        result = {"state": self.state(root), "generations": [], "candidates": [], "attempts": [],
                  "events": events(root / "lifecycle.jsonl") + events(root / "events.jsonl"), "artifacts": []}
        for path in root.glob("worker-*.json"):
            result["events"].extend(read_json(path, []))
        recipe = next((item["recipe"] for item in result["events"] if item.get("event") == "managed_start"), {})
        workload = recipe.get("workload", recipe.get('numerical',{}).get('workload',{}))
        contexts={}
        db_path = root / "ledger.sqlite"
        checkpoint = result["state"].get("finalWeightsSha256")
        weights = data_root(root)/'weights'
        if db_path.exists():
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN")  # consistent projection, never mutate the runtime ledger
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='generation_context'").fetchone():
                    contexts={r['generation']:json.loads(r['body']) for r in db.execute('SELECT generation,body FROM generation_context')}
                for gen in db.execute("SELECT g.*, u.child_weights_sha256, u.applied_at FROM generation g LEFT JOIN generation_update u USING(experiment_id,generation) ORDER BY g.generation"):
                    if gen["applied_at"] and (weights / (gen["child_weights_sha256"] + ".bin")).is_file():
                        checkpoint = gen["child_weights_sha256"]
                    number = gen["generation"]
                    generation_id = f"{run_id}.g{number}"
                    rewards = [row[0] for row in db.execute("SELECT reward FROM result JOIN candidate USING(candidate_id) WHERE generation=?", (number,))]
                    count = db.execute("SELECT count(*) FROM candidate WHERE generation=?", (number,)).fetchone()[0]
                    row = {"experimentId": run_id, "generationId": generation_id, "modelVersion": gen["parent_weights_sha256"],
                           "status": "COMPLETED" if gen["applied_at"] else
                           result["state"]["status"] if result["state"].get("status") in ("CANCELLED", "FAILED") else "RUNNING", "candidateCount": count,
                           "committedCandidateCount": len(rewards), "completedAt": iso(gen["applied_at"])}
                    row["startedAt"] = next((iso(item["t"]) for item in result["events"]
                                             if item.get("event") == "generation_open" and item.get("generation") == number), None)
                    if rewards:
                        row.update(rewardMean=sum(rewards)/len(rewards), rewardBest=max(rewards))
                    if number in contexts:row['generationContext']=contexts[number]
                    result["generations"].append(row)
                for c in db.execute("SELECT c.*,g.recipe_hash,g.parent_weights_sha256,r.reward FROM candidate c JOIN generation g USING(experiment_id,generation) LEFT JOIN result r USING(candidate_id)"):
                    attempts = list(db.execute("SELECT attempt_number,worker_id,leased_at,deadline,ended_at,failure_kind FROM attempt WHERE candidate_id=? ORDER BY attempt_number", (c["candidate_id"],)))
                    # The UI ID is separate from canonical descriptor identity, which stays in the ledger.
                    cid = f"{run_id}.g{c['generation']}.c{c['candidate_index']}"
                    item = {"experimentId": run_id, "generationId": f"{run_id}.g{c['generation']}", "candidateId": cid,
                            "modelVersion": c["parent_weights_sha256"], "seed": str(c["seed"]), "noiseRecipeHash": c["recipe_hash"],
                            "generationConfigHash": workload.get("generation_config_sha256"),
                            "batchIds": [workload["hash"]] if workload.get("hash") else [], "status": c["state"]}
                    if c["reward"] is not None:
                        item["reward"] = c["reward"]
                    if c['generation'] in contexts:
                        item['batchIds']=[contexts[c['generation']]['batchHash']]
                        item['effectiveSigma']=contexts[c['generation']]['sigmaFloat32']
                    for a in attempts:
                        aid = cid + f".a{a['attempt_number']}"
                        success = db.execute("SELECT committed_at FROM result WHERE candidate_id=? AND attempt_number=?", (c["candidate_id"], a["attempt_number"])).fetchone()
                        expired = not a["ended_at"] and a["deadline"] < time.time()
                        result["attempts"].append({"experimentId": run_id, "generationId": item["generationId"], "candidateId": cid,
                            "attemptId": aid, "workerId": a["worker_id"], "modelVersion": c["parent_weights_sha256"],
                            "status": "SUCCEEDED" if success else "FAILED" if a["failure_kind"] or expired else "RUNNING",
                            "startedAt": iso(a["leased_at"]), "completedAt": iso(success[0] if success else a["ended_at"]),
                            "errorType": a["failure_kind"] or ("LEASE_EXPIRED" if expired else None)})
                        item.update(attemptId=aid, workerId=a["worker_id"], leaseDeadline=iso(a["deadline"]))
                    result["candidates"].append(item)
        for event in result["events"]:
            if event.get("candidate_id"):
                event["uiCandidateId"] = event["candidate_id"].replace("/", ".")
        allowed = [root / "config.json", root / "events.jsonl", root / "lifecycle.jsonl", *root.glob("summary-*.json"),*root.glob('validation-*.json'),*root.glob('study-*.json')]
        result['studyMetrics']=read_json(root/'study-metrics.json')
        result["checkpointSha256"] = checkpoint
        if checkpoint:
            allowed.append(weights / (checkpoint + ".bin"))
        for path in allowed:
            if path.is_file():
                name = path.name
                result["artifacts"].append({"artifactId": run_id + "." + name, "experimentId": run_id,
                    "name": name, "path": name, "type": "CHECKPOINT" if name.endswith(".bin") else
                    "CONFIG" if name == "config.json" else "EVALUATION_RESULTS", "status": "READY",
                    "sizeBytes": path.stat().st_size, "createdAt": iso(path.stat().st_mtime)})
        return result


def main():
    config = read_json(sys.argv[1])
    token = read_json(config["credentialsFile"])["runtime_token"]
    manager = Manager(config, token)
    manager.thread.start()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def reply(self, status, body):
            encoded = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        def dispatch(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, {"message": "unauthorized"}); return
            parts = self.path.strip("/").split("/")
            try:
                if self.command=='GET' and parts==['maintenance']:
                    return self.reply(200,{'hold':read_json(manager.root/'maintenance.json')})
                if self.command=='POST' and parts in (['maintenance','acquire'],['maintenance','release'],['backups']):
                    length=int(self.headers.get('Content-Length',0))
                    if length>16384:
                        raise ValueError('invalid request length')
                    body=json.loads(self.rfile.read(length)) if length else {}
                    if parts==['maintenance','acquire']:
                        return self.reply(200,manager.acquire_maintenance())
                    if parts==['maintenance','release']:
                        return self.reply(200,manager.release_maintenance(body['maintenanceId']))
                    return self.reply(201,manager.create_backup(body['maintenanceId']))
                if self.command=='GET' and len(parts)==2 and parts[0]=='backups':
                    path=manager.backup_path(parts[1])
                    self.send_response(200)
                    self.send_header('Content-Length',str(path.stat().st_size))
                    self.send_header('Content-Type','application/x-tar')
                    self.end_headers()
                    with open(path,'rb') as stream:
                        while block:=stream.read(1024*1024):
                            self.wfile.write(block)
                    return
                if self.command=='DELETE' and len(parts)==2 and parts[0]=='backups':
                    return self.reply(200,manager.discard_backup(parts[1]))
                if self.command == "GET" and parts == ["capabilities"]:
                    return self.reply(200, {**capabilities(manager.workers),
                                           "quarantinedWorkerIds": list(read_json(manager.root / "quarantine.json", {}))})
                if self.command == "GET" and parts == ["workers"]:
                    return self.reply(200, manager.registry())
                if self.command == "GET" and parts == ["runs"]:
                    return self.reply(200, [{"runId": path.name, **manager.state(path)} for path in manager.root.iterdir() if path.is_dir()])
                if self.command == "POST" and parts == ["runs"]:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 < length <= 16384:
                        raise ValueError("invalid request length")
                    return self.reply(202, manager.submit(json.loads(self.rfile.read(length))))
                if len(parts) == 2 and parts[0] == "runs" and self.command == "GET":
                    return self.reply(200, manager.snapshot(parts[1]))
                if len(parts) == 3 and parts[0] == "runs" and parts[2] == "cancel" and self.command == "POST":
                    root = manager.directory(parts[1])
                    if not (root / "config.json").exists():
                        raise FileNotFoundError()
                    (root / "cancel.flag").touch()
                    return self.reply(202, manager.state(root))
                if len(parts) == 4 and parts[0] == "runs" and parts[2] == "artifacts" and self.command == "GET":
                    run_id, artifact = parts[1], parts[3]
                    snapshot = manager.snapshot(run_id)
                    entry = next((item for item in snapshot["artifacts"] if item["name"] == artifact), None)
                    if not entry:
                        raise FileNotFoundError()
                    root = manager.directory(run_id)
                    path = data_root(root) / "weights" / artifact if artifact.endswith(".bin") else root / artifact
                    self.send_response(200)
                    self.send_header("Content-Length", str(path.stat().st_size))
                    self.send_header("Content-Type", "application/octet-stream")
                    self.end_headers()
                    with open(path, "rb") as stream:
                        while block := stream.read(1024 * 1024):
                            self.wfile.write(block)
                    return
                self.reply(404, {"message": "route not found"})
            except FileNotFoundError:
                self.reply(404, {"message": "run/artifact not found"})
            except (ValueError, TypeError, KeyError) as error:
                self.reply(422, {"message": str(error)})
            except RuntimeError as error:
                self.reply(409, {"message": str(error)})
        do_GET = dispatch
        do_POST = dispatch
        do_DELETE = dispatch
    ThreadingHTTPServer(("127.0.0.1", config.get("controlPort", 8766)), Handler).serve_forever()


if __name__ == "__main__":
    main()
