"""Outbound device agent. Typed commands, boot-scoped opt-in, owned processes only."""

import argparse
import base64
import hashlib
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import sys
import time
import threading
import urllib.error
import urllib.request
import uuid
from heteroes.http_transport import USER_AGENT
from .files import events, read_json, write_json
from .run_supervisor import MAX_LAUNCHES, RunSupervisor, TERMINAL, QUIESCENT, ROOT, launched, validate
from .remote import alive, identity, worker_environment, handle as remote_handle
from .platform_process import acquire_instance_lock, ProcessIdentityUnknown, spawn_options
from .storage import data_root, worker_cache

COMMAND_KINDS = frozenset(
    {
        "SET_CONTRIBUTION",
        "COORDINATE",
        "START_WORKER",
        "STOP_WORKER",
        "CANCEL_ASSIGNMENT",
        "UPDATE_BACKUP_POLICY",
        "UPDATE_MEMBERSHIP",
        "PAUSE_ASSIGNMENT",
        "QUALIFY_MODEL",
        "CANCEL_MODEL_QUALIFICATION",
    }
)


def membership_change(change):
    """A lab request to add or remove a worker of a running experiment (ADR-009), or InvalidCommand: it can never succeed."""
    if not isinstance(change, dict):
        raise InvalidCommand("Invalid membership change")
    allowed = {"changeId", "workerId", "action", "actor", "grant"}
    texts = ("changeId", "workerId", "actor")
    if (
        set(change) - allowed
        or not set(texts) <= set(change)
        or any(not isinstance(change[key], str) or not change[key] or len(change[key]) > 200 for key in texts)
        or change.get("action") not in ("JOIN", "LEAVE")
    ):
        raise InvalidCommand("Invalid membership change")
    grant = change.get("grant")
    if change["action"] == "JOIN" and (not isinstance(grant, str) or not grant):
        raise InvalidCommand("A joining worker needs its compute credential")
    return {key: change[key] for key in texts + ("action",)} | ({"grant": grant} if change["action"] == "JOIN" else {})


def request(url, path, token, body, method=None):
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **({"X-HeteroES-Agent-Commands": ",".join(sorted(COMMAND_KINDS))} if path == "/api/v1/device/poll" else {}),
        },
    )
    # Never expose exception URLs, token-bearing bodies or server tracebacks.
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def reachable(url, token, timeout=4):
    """True if a coordinator answers /v1/health with this grant. No proxy, like the worker's own client."""
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/v1/health", headers={"Authorization": "Bearer " + token, "User-Agent": USER_AGENT}
        )
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as response:
            return response.status == 200 and json.load(response).get("ok") is True
    except Exception:
        return False


class InvalidCommand(ValueError):
    """Unknown kind or malformed identity: retrying can never succeed, so it is acknowledged."""


# The counter table of each event the agent raises about a command that did not finish.
PROBLEM_TABLES = {"agent_command_failed": "command_failures", "agent_command_deferred": "command_deferrals"}


def public_reason(error):
    """The agent's own words for the lab, at most 200 characters. Only the agent's own error types are described:
    a network or OS error may carry a grant URL or a private path. URLs are masked in any case."""
    if type(error) not in (ValueError, RuntimeError, InvalidCommand):
        return None
    return re.sub(r"\b[a-z][a-z0-9+.-]*://\S+", "<url>", str(error))[:200]


def owned_state(record, intent=False):
    if record is None:
        return None if intent else False
    if record.get("birth") is None or type(record.get("pid")) is not int:
        return None
    try:
        return alive(record)
    except ProcessIdentityUnknown:
        return None


def bounded_snapshot(snapshot, max_bytes=1_250_000):
    """Bound heartbeat detail while preserving final state and global counters.

    Complete events are spooled separately before this projection is reduced.
    Full candidate history remains in the canonical ledger/recovery points.
    """
    generations = snapshot["generations"]
    snapshot["completedGenerationCount"] = sum(g["status"] == "COMPLETED" for g in generations)
    snapshot["latestGeneration"] = generations[-1] if generations else None

    def size():
        return len(json.dumps(snapshot, allow_nan=False).encode())

    for key in ("events", "attempts", "candidates", "generations"):
        while snapshot[key] and size() > max_bytes:
            snapshot[key] = snapshot[key][max(1, len(snapshot[key]) // 2) :]
            snapshot["monitoringPartial"] = True
    while snapshot.get("artifactContents") and size() > max_bytes:
        largest = max(snapshot["artifactContents"], key=lambda k: len(snapshot["artifactContents"][k]["base64"]))
        del snapshot["artifactContents"][largest]
        snapshot["monitoringPartial"] = True
    if size() > max_bytes:
        raise ValueError("Runtime state exceeds the monitoring budget")
    return snapshot


class AgentManager(RunSupervisor):
    def __init__(self, agent):
        self.agent = agent
        bind = f"http://{agent.config.get('workerHost', '127.0.0.1')}:{agent.config.get('workerPort', 8765)}"
        cfg = {
            **agent.config,
            "python": sys.executable,
            "workerUrl": bind,
            "stateDirectory": str(agent.root / "runs"),
            "workers": [],
        }
        super().__init__(cfg, secrets.token_urlsafe(32))
        self._launch = self.spawn

    def spawn(self, root):
        import subprocess

        env = worker_environment(str(ROOT / "src"), self.token)
        device = self.config.get("device", "cuda")
        if device not in ("cpu", "cuda"):
            raise ValueError("Invalid coordinator device")
        if device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""
        with open(root / "coordinator.log", "ab") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "heteroes.product.runner", str(root), "--device", device],
                env=env,
                cwd=ROOT,
                stdout=output,
                stderr=output,
                **spawn_options(),
            )
        self.processes[root.name] = process
        write_json(root / "process.json", {"pid": process.pid, "birth": identity(process.pid)})

    def cancel(self, run_id):
        root = self.directory(run_id)
        if (root / "config.json").exists():
            (root / "cancel.flag").touch(mode=0o600)

    def launch(self, root):
        if self.agent.enabled:
            if self.agent.probes.busy():
                raise RuntimeError("Wait for model probe GPU release before training")
            intent = read_json(root / "launch-intent.json")
            if intent and (intent.get("process") is None or owned_state(intent["process"]) is not False):
                raise RuntimeError("Coordinator launch ownership is unknown")
            (root / "dispatch-held.flag").unlink(missing_ok=True)
            write_json(root / "launch-intent.json", {"process": None})
            self._launch(root)
            write_json(root / "launch-intent.json", {"process": read_json(root / "process.json")})

    def remote(self, worker, body):
        # Current ownership stays on this coordinator. The CPU server only relays
        # fixed worker lifecycle commands; it never evaluates a candidate.
        action = body["action"]
        run = body.get("runId")
        if run:
            run_id, recovery = run.rsplit("-r", 1)
            recovery = int(recovery)
        else:
            pending = [r for r in self.root.iterdir() if r.is_dir() and self.state(r).get("status") not in QUIESCENT]
            if len(pending) != 1:
                raise RuntimeError("No unique active assignment")
            run_id = pending[0].name
            recovery = self.state(pending[0]).get("recoveryCount", 0)
        ar = read_json(self.directory(run_id) / "assignment.json")
        result = self.agent.call(
            "/api/v1/device/worker-command",
            {
                "assignmentId": ar["assignmentId"],
                "epoch": ar["epoch"],
                "workerId": worker["id"],
                "action": action,
                "recoveryIndex": recovery,
                **launched(body.get("launch", 0)),
            },
        )
        if action != "probe" and result.get("alive") is None:
            raise ConnectionError("Worker ownership is unknown")
        return result

    def start_worker(self, root, worker, recovery, launch=0):
        return self.remote(worker, {"action": "start", "runId": root.name + f"-r{recovery}", **launched(launch)})

    def accept(self, command):
        cfg = command["config"]
        self.workers = {wid: {"id": wid} for wid in cfg["workerIds"]}
        validate(cfg, self.workers)
        self.submit(cfg)
        root = self.directory(cfg["runId"])
        previous = read_json(root / "assignment.json")
        if previous and (previous["assignmentId"], previous["epoch"]) != (command["assignmentId"], command["epoch"]):
            if command["epoch"] != previous["epoch"] + 1 or previous["config"] != cfg:
                raise ValueError("Resume must preserve configuration and advance one epoch")
            if (
                self.state(root).get("status") != "PAUSED"
                or owned_state(read_json(root / "process.json"), (root / "launch-intent.json").exists()) is not False
            ):
                raise RuntimeError("Resume requires confirmed paused coordinator shutdown")
            if any(
                not value.get("notStarted") and (value.get("alive") or not value.get("confirmed"))
                for value in self.state(root).get("workerStates", {}).values()
            ):
                raise RuntimeError("Resume requires confirmed worker shutdown")
            from .recovery import verify_point

            paused = read_json(root / "pause-point.json")
            if not paused or paused != command.get("resumeFrom"):
                raise ValueError("Resume checkpoint lineage mismatch")
            manifest = verify_point(data_root(root) / "recovery-points" / paused["pointId"])
            if (
                manifest["childWeightsSha256"] != paused["childWeightsSha256"]
                or manifest["generation"] != paused["generation"]
            ):
                raise ValueError("Resume checkpoint bytes changed")
            # Keep canonical ledger/weights and append-only evidence. Only local
            # process/handshake state belongs to the new assignment epoch.
            for name in (
                "runner.json",
                "process.json",
                "start.flag",
                "workers-stopped.flag",
                "pause.flag",
                "cancel.flag",
                "launch-intent.json",
            ):
                (root / name).unlink(missing_ok=True)
            self.save(
                root, status="STARTING", recoveryCount=0, workersLaunched=False, workerStates={}, failureReason=None
            )
            self.log(root, "resume_assignment", epoch=command["epoch"], assignmentId=command["assignmentId"])
        write_json(root / "assignment.json", command)
        write_json(root / "device-grants.json", command["computeGrants"])
        write_json(
            root / "backup-policy.json",
            command.get("effectiveBackupPolicy", cfg.get("backupPolicy", {"interval": 1, "retain": 3})),
        )
        # Operational settings are local/private, outside canonical Recipe v1.
        local = read_json(root / "config.json")
        local.update(backupPolicy=cfg.get("backupPolicy", {"interval": 1, "retain": 3}), deviceCredentials=True)
        if cfg.get("recipeVersion") in (2, 3):
            from heteroes.study.prepare import prepare

            try:
                local.update(prepare(self.agent, command, cfg, root))
            except Exception as error:
                # a run that cannot get its inputs must not keep the GPU pool in STARTING; only our own messages are
                # shown (a network error may carry a grant URL)
                reason = f"{type(error).__name__}: {error}" if type(error) in (ValueError, RuntimeError) else None
                self.save(root, status="FAILED", failureReason=reason or type(error).__name__)
                raise
        write_json(root / "config.json", local)

    def tick(self, root):
        # Reload only our locally accepted assignment, including after agent restart.
        ar = read_json(root / "assignment.json")
        if not ar:
            return
        membership = read_json(root / "membership.json", {})  # workers that joined or left while it runs (ADR-009)
        self.workers = {
            w: {"id": w}
            for w in [*ar["config"]["workerIds"], *membership.get("members", []), *membership.get("left", [])]
        }
        # Dead-process recovery must wait for this boot's owner opt-in. A living
        # child can still be adopted/observed and reach normal shutdown while OFF.
        if (
            not self.agent.enabled
            and not alive(read_json(root / "process.json"))
            and read_json(root / "runner.json", {}).get("status") not in QUIESCENT
        ):
            return
        if owned_state(read_json(root / "process.json"), (root / "launch-intent.json").exists()) is None:
            self.save(root, status="RECOVERING", failureReason="Coordinator process identity is unknown")
            return
        if ar["config"].get("recipeVersion") in (2, 3) and "datasetPath" not in read_json(root / "config.json", {}):
            return  # accept() is still transferring the dataset and model: the coordinator reads their paths
        super().tick(root)


class Agent:
    def __init__(self, path, lock=False, config_override=None):
        self.path = Path(path)
        self.config = {**read_json(path), **(config_override or {})}
        self.root = Path(self.config["stateDirectory"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.instance_lock = None
        if lock:
            self.instance_lock = acquire_instance_lock(self.root / "agent.lock")
        self.desktop_lock = threading.RLock()
        self.boot_id = uuid.uuid4().hex
        self.enabled = False
        self.stopping = False
        self.shutdown_requested = False
        write_json(self.root / "boot.json", {"bootId": self.boot_id, "enabled": False})
        from .telemetry import TelemetrySampler

        self.last_rtt_ms = None
        self.telemetry_supported = False
        self.detailed_telemetry_supported = False
        self.telemetry = TelemetrySampler(
            self.root,
            self.config.get("largeDataDirectory"),
            self.config.get("selfTest", {}).get("gpuUUID"),
            Path.home() / ".local/share/heteroes-power",
        )
        self.manager = AgentManager(self)
        from .model_probe_agent import ModelProbeManager

        self.probes = ModelProbeManager(self)
        self.model_qualification_supported = False
        self.db_path = self.root / "outbox.sqlite"
        with self.db() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS processed(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS released(assignment_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS event_outbox(id TEXT PRIMARY KEY,assignment_id TEXT NOT NULL,epoch INTEGER NOT NULL,body TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sequence(assignment_id TEXT PRIMARY KEY,value INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(assignment_id TEXT PRIMARY KEY,sequence INTEGER NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS command_failures(id TEXT PRIMARY KEY,kind TEXT NOT NULL,error_type TEXT NOT NULL,attempts INTEGER NOT NULL,last_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS command_deferrals(id TEXT PRIMARY KEY,kind TEXT NOT NULL,error_type TEXT NOT NULL,attempts INTEGER NOT NULL,last_at REAL NOT NULL);""")
        with self.db() as db:
            if "ack" not in {r[1] for r in db.execute("PRAGMA table_info(event_outbox)")}:
                db.execute("ALTER TABLE event_outbox ADD COLUMN ack INTEGER NOT NULL DEFAULT 0")
        os.chmod(self.db_path, 0o600)
        # One agent owns this state directory. Kernel lock is released on a crash.

    def db(self):
        return sqlite3.connect(self.db_path)

    def call(self, path, body, method=None):
        return request(self.config["serverUrl"], path, self.config["deviceToken"], body, method=method)

    def worker_directory(self, command):
        run_id = command.get("runId")
        if (
            not re.fullmatch("[a-f0-9]{32}", command.get("assignmentId", ""))
            or type(command.get("epoch")) is not int
            or command["epoch"] < 1
        ):
            raise InvalidCommand("Invalid assignment identity")
        if run_id is not None and not re.fullmatch("[a-f0-9]{32}", run_id):
            raise InvalidCommand("Invalid run identity")
        recovery = command.get("recoveryIndex", 0)
        if type(recovery) is not int or recovery not in (0, 1):
            raise InvalidCommand("Invalid recovery attempt")
        launch = command.get("launch", 0)
        if type(launch) is not int or not 0 <= launch < MAX_LAUNCHES:
            raise InvalidCommand("Invalid worker launch")
        return (
            self.root / "workers" / command["assignmentId"] / (f"r{recovery}-l{launch}" if launch else f"r{recovery}")
        )

    def _worker(self, command, action):
        from .cpu_coordinator import coordinator_only

        if action == "start" and (
            self.config.get("device") == "cpu" or coordinator_only(self.config.get("selfTest", {}))
        ):
            raise ValueError("CPU coordinator-only devices cannot start workers")
        directory = self.worker_directory(command)
        original = read_json(directory / "assignment.json")
        if action == "start":
            if not self.enabled:
                raise RuntimeError("Contribution is OFF for this boot")
            if self.probes.busy():
                raise RuntimeError("Wait for model probe GPU release before training")
            if command["workerId"] != self.config["workerId"]:
                raise ValueError("Worker identity mismatch")
            if original and original != command:
                raise ValueError("Frozen worker assignment changed")
            for earlier in range(command.get("launch", 0)):
                # a restart never runs beside an earlier launch of this run on this device
                old = self.worker_directory({**command, "launch": earlier})
                if owned_state(read_json(old / "process.json"), (old / "launch-intent.json").exists()) is not False:
                    raise RuntimeError("An earlier launch of this worker may still be running")
            if original is None:
                # Persist ownership before launch so a lost ack is idempotent.
                write_json(directory / "assignment.json", command)
            study = {}
            if command.get("studyConfig"):
                from heteroes.study.prepare import prepare

                study = prepare(self, command, command["studyConfig"], directory)
            route = self.choose_route(command)
            argv = [
                sys.executable,
                str(ROOT / "scripts/run_worker.py"),
                "--coordinator-url",
                route["coordinatorUrl"],
                "--worker-id",
                self.config["workerId"],
                "--model-path",
                study.get("modelPath", self.config["modelPath"]),
                "--log",
                str(directory / "events.jsonl"),
                "--replay",
                "always",
                "--replay-verify-every",
                "1",
                "--cache-dir",
                str(worker_cache(directory, self.config)),
                "--give-up-after-seconds",
                "120",
                *([] if study and command["studyConfig"].get("recipeVersion") == 3 else ["--chunk", "16"]),
                "--stop-file",
                str(directory / "stop-request.json"),
            ]
            if route["bulkUrl"]:
                argv.extend(["--bulk-url", route["bulkUrl"]])
            if route["replayOnly"]:
                # Other network: update records only. 64 steps is about five minutes of catching up on a 3060.
                argv.extend(["--no-bulk", "--replay-max-chain", "64"])
            if study and command["studyConfig"].get("recipeVersion") == 3:
                write_json(directory / "run-config.json", command["studyConfig"])
                argv.extend(["--run-config", str(directory / "run-config.json")])
            if study:
                argv.extend(["--dataset", study["datasetPath"], "--model-manifest", study["modelManifestPath"]])
            if self.config.get("largeDataDirectory") and self.config.get("storageVolumeUUID"):
                argv.extend(["--storage-volume-uuid", self.config["storageVolumeUUID"]])
            if (directory / "launch-intent.json").exists() and not (directory / "process.json").exists():
                raise RuntimeError("Worker launch ownership is unknown")
            return remote_handle(
                {
                    "action": "start",
                    "directory": str(directory),
                    "source": str(ROOT / "src"),
                    "token": command["computeToken"],
                    "argv": argv,
                }
            )
        if original is None:
            return {"alive": False, "ready": False, "events": []}
        result = remote_handle({"action": action, "directory": str(directory)})
        result["alive"] = owned_state(
            read_json(directory / "process.json"), (directory / "launch-intent.json").exists()
        )
        return result

    def choose_route(self, command):
        """The private route when it answers (replay and full download); else the lab's public one, which
        carries replay but never whole weights. A lab with no public address keeps the command as it was."""
        private, bulk, public, token = (
            command["coordinatorUrl"],
            command.get("bulkUrl"),
            command.get("publicComputeUrl"),
            command["computeToken"],
        )
        if not public or reachable(private, token):
            return {"coordinatorUrl": private, "bulkUrl": bulk, "replayOnly": False}
        if reachable(public, token):
            return {"coordinatorUrl": public, "bulkUrl": None, "replayOnly": True}
        raise RuntimeError("The coordinator is not reachable on any route yet")

    def handle(self, command):
        kind = command.get("kind")
        if kind not in COMMAND_KINDS:
            raise InvalidCommand("Unsupported device command")
        cid = command.get("commandId")
        if not isinstance(cid, str) or not cid:
            raise InvalidCommand("Missing command identity")
        with self.db() as db:
            if db.execute("SELECT 1 FROM processed WHERE id=?", (cid,)).fetchone():
                return
            if (
                kind in ("COORDINATE", "START_WORKER", "PAUSE_ASSIGNMENT", "UPDATE_BACKUP_POLICY", "UPDATE_MEMBERSHIP")
                and db.execute(
                    "SELECT 1 FROM released WHERE assignment_id=?", (command.get("assignmentId"),)
                ).fetchone()
            ):
                db.execute("INSERT OR IGNORE INTO processed VALUES (?)", (cid,))
                return
        if kind == "SET_CONTRIBUTION":
            if command["bootId"] == self.boot_id:
                if command["enabled"] and self.shutdown_requested:
                    raise RuntimeError("Desktop shutdown is pending")
                self.enabled = bool(command["enabled"])
                write_json(self.root / "boot.json", {"bootId": self.boot_id, "enabled": self.enabled})
                if not self.enabled:
                    self.cancel_all()
        elif kind == "QUALIFY_MODEL":
            self.probes.start(command)
        elif kind == "CANCEL_MODEL_QUALIFICATION":
            self.probes.cancel(command.get("jobId"))
        elif kind == "COORDINATE":
            if self.config.get("workerOnly"):
                raise ValueError("This device profile is worker-only")
            self.worker_directory(command)
            if self.cancelled(command):
                with self.db() as db:
                    db.execute("INSERT OR IGNORE INTO processed VALUES (?)", (cid,))
                return
            if not self.enabled:
                raise RuntimeError("Contribution is OFF for this boot")
            if self.probes.busy():
                raise RuntimeError("Wait for model probe GPU release before training")
            if command["coordinatorDeviceId"] != self.config["deviceId"]:
                raise ValueError("Coordinator identity mismatch")
            self.manager.accept(command)
        elif kind in ("UPDATE_BACKUP_POLICY", "PAUSE_ASSIGNMENT"):
            self.worker_directory(command)
            matched = False
            for root in self.manager.root.iterdir():
                ar = read_json(root / "assignment.json") if root.is_dir() else None
                if ar and (ar["assignmentId"], ar["epoch"]) == (command["assignmentId"], command["epoch"]):
                    if kind == "PAUSE_ASSIGNMENT":
                        (root / "pause.flag").touch(mode=0o600)
                        matched = True
                        continue
                    policy = command["policy"]
                    if set(policy) != {"interval", "retain"} or any(
                        type(v) is not int or not 1 <= v <= 1000 for v in policy.values()
                    ):
                        raise ValueError("Invalid backup policy")
                    write_json(root / "backup-policy.json", policy)
                    matched = True
            if not matched:
                raise RuntimeError("Wait for the assignment before applying its policy")
        elif kind == "UPDATE_MEMBERSHIP":
            self.worker_directory(command)
            change = membership_change(command.get("change"))
            for root in self.manager.root.iterdir():
                ar = read_json(root / "assignment.json") if root.is_dir() else None
                if ar and (ar["assignmentId"], ar["epoch"]) == (command["assignmentId"], command["epoch"]):
                    # the runner applies it at the next generation boundary and records it in the ledger (ADR-009)
                    requests = read_json(root / "membership-requests.json", {"requests": []})["requests"]
                    if all(item.get("changeId") != change["changeId"] for item in requests):
                        write_json(root / "membership-requests.json", {"requests": [*requests, change]})
                    break
            else:
                raise RuntimeError("Wait for the assignment before changing its members")
        elif kind == "START_WORKER":
            self.worker_directory(command)
            if not self.cancelled(command):
                self._worker(command, "start")
        elif kind == "STOP_WORKER":
            self._worker(command, "stop")
        elif kind == "CANCEL_ASSIGNMENT":
            self.worker_directory(command)
            write_json(
                self.root / "cancelled-assignments" / f"{command['assignmentId']}.json",
                {"assignmentId": command["assignmentId"], "epoch": command["epoch"]},
            )
            for root in self.manager.root.iterdir():
                ar = read_json(root / "assignment.json") if root.is_dir() else None
                if ar and (ar["assignmentId"], ar["epoch"]) == (command["assignmentId"], command["epoch"]):
                    self.manager.cancel(root.name)
            for directory in (self.root / "workers" / command["assignmentId"]).glob("r*"):
                ar = read_json(directory / "assignment.json")
                if ar and ar["epoch"] == command["epoch"]:
                    self._worker(ar, "stop")
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO processed VALUES (?)", (cid,))

    def run_commands(self, commands):
        """One command never blocks the others. A command that can never succeed (unknown kind,
        malformed identity) is acknowledged; any other failure stays unacknowledged and is retried."""
        for command in commands:
            try:
                self.handle(command)
            except RuntimeError as error:
                self.record_deferral(command, error)  # OFF/deferred commands remain unacknowledged
            except InvalidCommand as error:
                self.record_failure(command, error)
                cid = command.get("commandId") if isinstance(command, dict) else None
                if isinstance(cid, str) and cid:
                    with self.db() as db:
                        db.execute("INSERT OR IGNORE INTO processed VALUES (?)", (cid,))
            except Exception as error:
                self.record_failure(command, error)

    def record_failure(self, command, error):
        """Count the failure; tell the server about an assignment's command at attempts 1, 10, 100, 1000."""
        self.record_problem("agent_command_failed", command, error)

    def record_deferral(self, command, error):
        """Same for a command that has to wait (contribution OFF, coordinator not reachable yet): counted apart
        from failures, still unacknowledged, but no longer silent."""
        self.record_problem("agent_command_deferred", command, error)

    def record_problem(self, event, command, error):
        command = command if isinstance(command, dict) else {}
        cid = command.get("commandId")
        if not isinstance(cid, str) or not cid:
            return
        kind = str(command.get("kind"))[:60]
        name = type(error).__name__
        table = PROBLEM_TABLES[event]
        with self.db() as db:
            db.execute(f"INSERT OR IGNORE INTO {table} VALUES (?,?,?,0,0)", (cid, kind, name))
            db.execute(
                f"UPDATE {table} SET attempts=attempts+1,error_type=?,last_at=? WHERE id=?",
                (name, time.time(), cid),
            )
            attempts = db.execute(f"SELECT attempts FROM {table} WHERE id=?", (cid,)).fetchone()[0]
            assignment = command.get("assignmentId")
            epoch = command.get("epoch")
            if (
                attempts in (1, 10, 100, 1000)
                and isinstance(assignment, str)
                and re.fullmatch("[a-f0-9]{32}", assignment)
                and type(epoch) is int
                and epoch >= 1
            ):
                body = {
                    "event": event,
                    "commandId": cid,
                    "kind": kind,
                    "errorType": name,
                    "attempts": attempts,
                    "t": round(time.time(), 3),
                }
                reason = public_reason(error)
                if reason:
                    body["reason"] = reason
                encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
                db.execute(
                    "INSERT OR IGNORE INTO event_outbox(id,assignment_id,epoch,body) VALUES (?,?,?,?)",
                    (hashlib.sha256((assignment + encoded).encode()).hexdigest(), assignment, epoch, encoded),
                )

    def cancelled(self, command):
        marker = read_json(self.root / "cancelled-assignments" / f"{command['assignmentId']}.json")
        return marker and marker["epoch"] == command["epoch"]

    def cancel_all(self):
        self.probes.cancel_all()
        for root in self.manager.root.iterdir():
            if (
                root.is_dir()
                and read_json(root / "config.json")
                and self.manager.state(root).get("status") not in QUIESCENT
            ):
                self.manager.cancel(root.name)
        for directory in (self.root / "workers").glob("*/r*"):
            ar = read_json(directory / "assignment.json")
            if ar:
                self._worker(ar, "stop")

    def observe(self):
        combined = {}
        with self.db() as db:
            released = {r[0] for r in db.execute("SELECT assignment_id FROM released")}
        for root in self.manager.root.iterdir():
            ar = read_json(root / "assignment.json") if root.is_dir() else None
            if not ar:
                continue
            key = ar["assignmentId"]
            if key in released:
                continue
            state = self.manager.state(root)
            recovery = state.get("recoveryCount", 0)
            combined[key] = {
                "assignmentId": key,
                "epoch": ar["epoch"],
                "coordinatorAlive": owned_state(
                    read_json(root / "process.json"), (root / "launch-intent.json").exists()
                ),
                # a stopped coordinator starts no worker: without a worker directory (below) none ever ran here, so
                # the lab can release a run that failed before its workers started
                "workerAlive": False if state.get("status") in QUIESCENT else None,
                "ready": False,
                "recoveryIndex": recovery,
                "events": [],
            }
            snap = self.manager.snapshot(root.name)
            # Keep a durable latest snapshot per assignment, not an unbounded copy
            # of the whole ledger projection every heartbeat during an outage.
            with self.db() as db:
                for event in snap["events"]:
                    encoded = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    eid = hashlib.sha256((key + encoded).encode()).hexdigest()
                    db.execute(
                        "INSERT OR IGNORE INTO event_outbox(id,assignment_id,epoch,body) VALUES (?,?,?,?)",
                        (eid, key, ar["epoch"], encoded),
                    )
            snap["events"] = snap["events"][-2000:]
            snap["artifactContents"] = {}
            for artifact in snap["artifacts"]:
                name = artifact["name"]
                path = root / name
                if path.is_file() and name.endswith((".json", ".jsonl")) and path.stat().st_size <= 262144:
                    data = path.read_bytes()
                    snap["artifactContents"][name] = {
                        "base64": base64.b64encode(data).decode(),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
            snap["cloudSync"] = read_json(root / "cloud-sync.json", {"status": "PENDING"})
            snap = bounded_snapshot(snap)
            with self.db() as db:
                row = db.execute("SELECT value FROM sequence WHERE assignment_id=?", (key,)).fetchone()
                sequence = (row[0] if row else 0) + 1
                db.execute("INSERT OR REPLACE INTO sequence VALUES (?,?)", (key, sequence))
                report = {"sequence": sequence, "assignmentId": key, "epoch": ar["epoch"], "snapshot": snap}
                db.execute("INSERT OR REPLACE INTO outbox VALUES (?,?,?)", (key, sequence, json.dumps(report)))
        for directory in (self.root / "workers").glob("*/r*"):
            ar = read_json(directory / "assignment.json")
            if not ar:
                continue
            key = ar["assignmentId"]
            if key in released:
                continue
            old = combined.get(key)
            if old and (ar["recoveryIndex"], ar.get("launch", 0)) < (old["recoveryIndex"], old.get("launch", 0)):
                continue  # the newest launch is the one the lab asks about
            p = self._worker(ar, "poll")
            old = {k: v for k, v in (old or {}).items() if k != "launch"}
            combined[key] = {
                **(old or {"assignmentId": key, "epoch": ar["epoch"], "coordinatorAlive": False}),
                "workerAlive": p["alive"],
                "ready": p["ready"],
                "recoveryIndex": ar["recoveryIndex"],
                **launched(ar.get("launch", 0)),
                "events": p["events"][-200:],
            }
        for path in (self.root / "cancelled-assignments").glob("*.json"):
            marker = read_json(path)
            key = marker["assignmentId"]
            if key not in combined and key not in released:
                combined[key] = {
                    **marker,
                    "coordinatorAlive": False,
                    "workerAlive": False,
                    "ready": False,
                    "recoveryIndex": 0,
                    "events": [],
                }
        return list(combined.values())

    def cycle(self):
        processes = self.observe()
        with self.db() as db:
            reports = [json.loads(r[0]) for r in db.execute("SELECT body FROM outbox ORDER BY rowid LIMIT 1")]
            event_batch = [
                {"eventId": r[0], "assignmentId": r[1], "epoch": r[2], "event": json.loads(r[3])}
                for r in db.execute(
                    "SELECT id,assignment_id,epoch,body FROM event_outbox WHERE ack=0 ORDER BY rowid LIMIT 500"
                )
            ]
            while len(json.dumps(event_batch).encode()) > 512_000:
                event_batch = event_batch[: max(0, len(event_batch) // 2)]
            acknowledgements = [r[0] for r in db.execute("SELECT id FROM processed ORDER BY rowid DESC LIMIT 100")]
        telemetry = {
            **self.telemetry.sample(),
            "transport": {
                "latencyMs": self.last_rtt_ms,
                "pendingReports": len(reports),
                "pendingEvents": len(event_batch),
            },
        }
        write_json(self.root / "telemetry.json", telemetry)
        wire_telemetry = telemetry
        if not self.detailed_telemetry_supported:
            from .telemetry import legacy_observation

            wire_telemetry = legacy_observation(telemetry)
        poll_started = time.monotonic()
        response = self.call(
            "/api/v1/device/poll",
            {
                **({"telemetry": wire_telemetry} if self.telemetry_supported else {}),
                "bootId": self.boot_id,
                "contribution": self.enabled,
                "processes": processes[:10],
                "reports": reports,
                "events": event_batch,
                "acknowledgements": acknowledgements,
                **({"qualificationReports": self.probes.reports()} if self.model_qualification_supported else {}),
                **({"selfTest": self.config["selfTest"]} if self.config.get("selfTest") else {}),
            },
        )
        self.last_rtt_ms = (time.monotonic() - poll_started) * 1000
        self.telemetry_supported = response.get("telemetrySupported") is True
        self.detailed_telemetry_supported = response.get("detailedTelemetrySupported") is True
        self.model_qualification_supported = response.get("modelQualificationSupported") is True
        self.probes.acknowledge(response.get("acceptedQualifications", []))
        # The first poll of a new boot always returns OFF. A user-authenticated
        # activation or typed command for the current boot is needed before launch.
        if response["approvalStatus"] == "REVOKED" or (self.enabled and not response["desiredContribution"]):
            self.enabled = False
            self.cancel_all()
        self.run_commands(response["commands"])
        with self.db() as db:
            for eid in response.get("acceptedEvents", []):
                db.execute("UPDATE event_outbox SET ack=1 WHERE id=?", (eid,))
            for aid in response.get("releasedAssignments", []):
                db.execute("INSERT OR IGNORE INTO released VALUES (?)", (aid,))
            for accepted in response["acceptedReports"]:
                db.execute(
                    "DELETE FROM outbox WHERE assignment_id=? AND sequence=?",
                    (accepted["assignmentId"], accepted["sequence"]),
                )
        return response

    def run(self):
        if self.instance_lock is None:
            self.instance_lock = acquire_instance_lock(self.root / "agent.lock")
        self.manager.thread.start()
        from .cloud_sync import CloudSync

        self.cloud_sync = CloudSync(self)
        self.cloud_sync.thread.start()
        while not self.stopping:
            try:
                with self.desktop_lock:
                    self.cycle()
                write_json(self.root / "connection.json", {"status": "ONLINE", "t": time.time()})
            except Exception as error:
                write_json(
                    self.root / "connection.json",
                    {"status": "OFFLINE", "errorType": type(error).__name__, "t": time.time()},
                )
            for _ in range(100):
                if self.stopping:
                    break
                time.sleep(0.1)
        self.cloud_sync.stop.set()
        self.cloud_sync.thread.join(timeout=2)
        self.manager.stop.set()
        self.manager.thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "on", "off", "status", "enroll"])
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = read_json(args.config)
    if args.action == "enroll":
        # Run the compatibility gate in a separate GPU process with the same
        # process-local WSL libraries used for actual workers.
        from .remote import worker_environment
        import subprocess

        code = getpass.getpass("One-use pairing code: ")
        env = worker_environment(str(ROOT / "src"), "self-test-no-network")
        result = subprocess.run(
            [sys.executable, "-m", "heteroes.product.selftest", config["modelPath"]],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode:
            raise SystemExit("Device self-test failed; inspect the local GPU environment")
        test = json.loads(result.stdout.splitlines()[-1])
        paired = request(
            config["serverUrl"],
            "/api/v1/device/enroll",
            "",
            {
                "code": code,
                "workerId": config["workerId"],
                "displayName": config.get("displayName", config["workerId"]),
                "computeUrl": config["computeUrl"],
                **({"bulkUrl": config["bulkUrl"]} if config.get("bulkUrl") else {}),
                "selfTest": test,
            },
        )
        config.update(deviceId=paired["deviceId"], deviceToken=paired["deviceToken"], selfTest=test)
        write_json(args.config, config)
        print("Enrolled; administrator approval required. Contribution is OFF.")
    elif args.action == "run":
        agent = Agent(args.config, lock=True)

        def stop(*_):
            agent.stopping = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        agent.run()
    elif args.action == "status":
        boot = read_json(Path(config["stateDirectory"]) / "boot.json", {})
        connection = read_json(Path(config["stateDirectory"]) / "connection.json", {})
        print(
            json.dumps(
                {
                    "workerId": config["workerId"],
                    "deviceId": config.get("deviceId"),
                    "boot": boot,
                    "connection": connection,
                },
                indent=2,
            )
        )
    else:
        username = input("Owner username: ")
        password = getpass.getpass("Owner password: ")
        session = request(config["serverUrl"], "/api/v1/auth/login", "", {"username": username, "password": password})
        boot = read_json(Path(config["stateDirectory"]) / "boot.json")
        request(
            config["serverUrl"],
            "/api/v1/devices/" + config["deviceId"] + "/contribution",
            session["accessToken"],
            {"enabled": args.action == "on", "bootId": boot["bootId"]},
        )
        request(config["serverUrl"], "/api/v1/auth/logout", session["accessToken"], {})
        print("Contribution change requested for the current boot.")


if __name__ == "__main__":
    main()
