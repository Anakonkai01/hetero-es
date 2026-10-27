"""Coordinator supervision shared by agent assignments; process launch and worker RPC are agent hooks."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.error

from heteroes.catalog import DECODE_ENGINES, SCHEDULER_POLICIES, SYNC_MODES, V3_DECODE_ENGINES, WORKLOAD_NAMES

from .files import events, read_json, write_json
from .remote import alive
from .storage import data_root, checked_directory

TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}
QUIESCENT = TERMINAL | {"PAUSED"}
ROOT = Path(__file__).resolve().parents[3]
WORKLOADS = WORKLOAD_NAMES
RESTART_SECONDS = 30  # a worker that is still away or OFF is asked again after this long
MAX_LAUNCH_ID = 1_000_000  # explicit retries keep unique process/command identities
MAX_LAUNCHES = 20  # launches of one worker in one coordinator recovery; a worker that keeps dying is then left alone
# a worker unreachable this long is taken as stopped when the run drains; before that an unknown state blocks the release
UNREACHABLE_STOP_SECONDS = 600
# a member unreachable this long while the run goes on is logged (once) and shown as lost on the timeline (finding 11)
UNREACHABLE_NOTICE_SECONDS = 120


def launched(launch):
    """The launch number in a worker state and a worker command: absent for the first one (older labs and agents)."""
    return {"launch": launch} if launch else {}


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if timestamp is not None else None


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
    if config.get("workload") not in WORKLOADS and not (
        config.get("recipeVersion") in (2, 3) and config.get("workload") in ("text_math_v2", "text_v3")
    ):
        raise ValueError("unsupported workload")
    decoders = V3_DECODE_ENGINES if config.get("recipeVersion") == 3 else DECODE_ENGINES
    if config.get("decodeEngine") not in decoders:
        raise ValueError("unsupported decoder")
    if config.get("recipeVersion") == 3:
        from heteroes.v3.options import validate_options

        # The coordinator runs the frozen researcher code (owner decision, ADR-008); it must arrive with the command.
        python = config["scorer"].get("kind") == "python" or any(
            str(config.get(key, "")).startswith("python@1:") for key in ("coefficientRule", "sampler")
        )
        validate_options(config, allow_python=python)
    selected = config.get("workerIds")
    if (
        not isinstance(selected, list)
        or not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= set(workers)
    ):
        raise ValueError("select unique configured worker IDs")
    if config.get("schedulerPolicy") not in SCHEDULER_POLICIES or config.get("syncMode") not in SYNC_MODES:
        raise ValueError(f"choose a scheduling policy among {', '.join(SCHEDULER_POLICIES)}, synchronously")


class RunSupervisor(ABC):
    def __init__(self, config, token):
        self.config, self.token = config, token
        self.root = Path(config["stateDirectory"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workers = {worker["id"]: worker for worker in config["workers"]}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.processes = {}  # reap owned children rather than leaking zombie processes
        self.retry_at = {}  # (run, worker) -> when a stopped member may be started again
        self.deferred = {}  # (run, worker) -> the last logged reason it could not be started again
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
            old = read_json(root / "config.json")
            if old:
                if any(old.get(key) != value for key, value in body.items()):
                    raise ValueError("run ID already belongs to a different configuration")
                return self.state(root)
            quarantined = read_json(self.root / "quarantine.json", {})
            if set(body["workerIds"]) & set(quarantined):
                raise ValueError(
                    "Selected worker is quarantined after a restore mismatch; administrator investigation required"
                )
            pending = [
                path
                for path in self.root.iterdir()
                if path.is_dir() and self.state(path).get("status") not in QUIESCENT
            ]
            if pending:
                raise RuntimeError("another run still owns the GPU pool")
            root.mkdir(mode=0o700)
            if self.config.get("largeDataDirectory"):
                try:
                    large = (
                        checked_directory(self.config["largeDataDirectory"], self.config.get("storageVolumeUUID"))
                        / "coordinators"
                        / body["runId"]
                    )
                    large.mkdir(parents=True, exist_ok=False, mode=0o700)
                    write_json(
                        root / "large-data.json",
                        {"directory": str(large), "volumeUUID": self.config.get("storageVolumeUUID")},
                    )
                except BaseException:
                    root.rmdir()
                    raise
            write_json(
                root / "config.json",
                {
                    **body,
                    "modelPath": self.config["modelPath"],
                    "host": self.config["workerHost"],
                    "port": self.config["workerPort"],
                },
            )
            self.save(root, status="STARTING", recoveryCount=0, startedAt=time.time(), workerStates={})
            return self.state(root)

    def poll_workers(self, root, stop=False):
        state = self.state(root)
        recovery = state.get("recoveryCount", 0)
        result = dict(state.get("workerStates", {}))
        for worker_id, previous in list(result.items()):
            if previous.get("stopReason") == "needs_private_route" and previous.get("alive") is False:
                continue
            if (
                previous.get("notStarted")
                or previous.get("left")
                or previous.get("lost")
                or previous.get("retryPending")
            ):
                continue  # never started, left the run and confirmed stopped (its GPU may serve another run now), or lost
            launch = previous.get("launch", 0)
            suffix = f"-l{launch}" if launch else ""
            try:
                value = self.remote(
                    self.workers[worker_id],
                    {"action": "stop" if stop else "poll", "runId": root.name + f"-r{recovery}", **launched(launch)},
                )
                write_json(root / f"worker-{worker_id}-r{recovery}{suffix}.json", value["events"])
                # D10: one restore fault followed by a successful recovery (the worker rejoined under its alias) does
                # not put the device aside; a second fault, a failed recovery or a quarantined exit does
                events = value["events"]
                faults = sum(item.get("failure") == "RESTORE_MISMATCH" for item in events)
                rejoined = any(item.get("event") == "restore_recovery_rejoined" for item in events)
                if (
                    any(item.get("reason") == "quarantined" for item in events)
                    or faults > 1
                    or (faults and not rejoined)
                ):
                    quarantined = read_json(self.root / "quarantine.json", {})
                    quarantined[worker_id] = {"runId": root.name, "t": time.time()}
                    write_json(self.root / "quarantine.json", quarantined)
                result[worker_id] = {
                    "alive": value["alive"],
                    "ready": value["ready"],
                    "confirmed": True,
                    **launched(launch),
                }
                self._record_worker_block(root, worker_id, result[worker_id], value.get("events", []))
                if previous.get("unreachableNoticed"):
                    self.log(
                        root, "worker_reachable", worker_id=worker_id, unreachableSince=previous["unreachableSince"]
                    )
            except Exception:
                if (
                    previous.get("startUnconfirmed")
                    and not stop
                    and self._resend_start(root, worker_id, result, recovery)
                ):
                    continue
                since = previous.get("unreachableSince") or time.time()
                if stop and time.time() - since >= UNREACHABLE_STOP_SECONDS:
                    result[worker_id] = {**previous, "alive": False, "confirmed": True, "lost": True}
                    self.log(root, "worker_lost", worker_id=worker_id, unreachableSince=since)
                else:
                    result[worker_id] = {**previous, "confirmed": False, "unreachableSince": since}
                    # tier 3: the 1660S stopped answering for 2 h 13 min and nothing said so until the drain
                    if time.time() - since >= UNREACHABLE_NOTICE_SECONDS and not previous.get("unreachableNoticed"):
                        result[worker_id]["unreachableNoticed"] = True
                        self.log(root, "worker_unreachable", worker_id=worker_id, unreachableSince=since)
        self.save(root, workerStates=result)
        return all(
            value.get("notStarted") or (value.get("confirmed") and not value.get("alive")) for value in result.values()
        )

    def _record_worker_block(self, root, worker_id, state, worker_events):
        """Temporary policy: public-route bulk recovery is not implemented yet.

        Keep this outside transient process state so recovery/OFF/ON/rejoin
        cannot accidentally authorize another identical failed replay.
        """
        if state.get("alive") is not False or not any(
            event.get("event") == "exit" and event.get("reason") == "needs_private_route" for event in worker_events
        ):
            return
        blocks = read_json(root / "worker-blocks.json", {})
        if worker_id not in blocks:
            blocks[worker_id] = {
                "reason": "needs_private_route",
                "blockedAt": time.time(),
                "launch": state.get("launch", 0),
            }
            write_json(root / "worker-blocks.json", blocks)
            self.log(root, "worker_blocked", worker_id=worker_id, reason="needs_private_route", temporary=True)
        state.update(stopReason=blocks[worker_id]["reason"], blockedAt=blocks[worker_id]["blockedAt"])

    def retry_worker(self, root, worker_id, request_id):
        """An explicit, idempotent request. Automatic recovery never calls this."""
        with self.lock:
            done = read_json(root / "worker-retries.json", [])
            if request_id in done:
                return
            state = self.state(root)
            membership = read_json(root / "membership.json", {})
            members = membership.get("members", read_json(root / "config.json")["workerIds"])
            if state.get("status") not in ("RUNNING", "STARTING") or worker_id not in members:
                raise ValueError("Retry requires a member of an active run")
            blocks = read_json(root / "worker-blocks.json", {})
            if worker_id not in blocks:
                raise ValueError("Worker is not blocked")
            values = dict(state.get("workerStates", {}))
            previous = values.get(worker_id, {})
            if previous.get("alive") is not False or previous.get("confirmed") is not True:
                raise RuntimeError("Retry requires confirmed worker shutdown")
            if previous.get("launch", 0) + 1 >= MAX_LAUNCH_ID:
                raise ValueError("Worker launch identity exhausted; start a new run")
            # Persist the consumed request before releasing the block. A retried
            # delivery must not clear a subsequent failure from the same launch.
            write_json(root / "worker-retries.json", [*done, request_id])
            blocks.pop(worker_id)
            write_json(root / "worker-blocks.json", blocks)
            values[worker_id] = {
                "alive": False,
                "ready": False,
                "confirmed": True,
                **launched(previous.get("launch", 0)),
                "retryPending": True,
            }
            self.save(root, workerStates=values)
            self.retry_at.pop((root.name, worker_id), None)
            self.log(root, "worker_retry_requested", worker_id=worker_id, requestId=request_id)

    def _start_one(self, root, worker_id, result, recovery):
        """Start one worker of this run (at preparation, or when it joins later) and record what is known about it."""
        block = read_json(root / "worker-blocks.json", {}).get(worker_id)
        if block:
            result[worker_id] = {
                "alive": False,
                "ready": False,
                "confirmed": True,
                "stopReason": block["reason"],
                "blockedAt": block["blockedAt"],
                **launched(block.get("launch", 0)),
            }
            self.save(root, workerStates=result)
            return
        if worker_id in read_json(self.root / "quarantine.json", {}):
            result[worker_id] = {"notStarted": True, "alive": False, "ready": False, "confirmed": True}
            self.log(root, "worker_quarantined", worker_id=worker_id)
            self.save(root, workerStates=result)
            return
        try:
            self.remote(self.workers[worker_id], {"action": "probe"})
        except Exception:
            result[worker_id] = {"notStarted": True, "alive": False, "ready": False, "confirmed": True}
            self.log(root, "worker_unavailable", worker_id=worker_id)
            self.save(root, workerStates=result)
            return
        self._launch_worker(root, worker_id, result, recovery, 0)

    def _launch_worker(self, root, worker_id, result, recovery, launch):
        # Persist unknown ownership before the worker command, since a connection may die after launch.
        result[worker_id] = {"alive": True, "confirmed": False, "ready": False, **launched(launch)}
        self.save(root, workerStates=result)
        try:
            value = self.start_worker(root, self.workers[worker_id], recovery, launch)
            result[worker_id] = {
                "alive": value["alive"],
                "confirmed": True,
                "ready": value["ready"],
                **launched(launch),
            }
            self._record_worker_block(root, worker_id, result[worker_id], value.get("events", []))
        except Exception as error:
            # The request may never have reached the lab (edge timeout): poll_workers sends this same launch again.
            result[worker_id]["startUnconfirmed"] = True
            # why it is unknown: the lab has not seen the worker yet (ConnectionError), or it refused (HTTP status)
            self.log(
                root,
                "worker_start_unknown",
                worker_id=worker_id,
                error=type(error).__name__,
                httpStatus=error.code if isinstance(error, urllib.error.HTTPError) else None,
            )
        self.save(root, workerStates=result)

    def _resend_start(self, root, worker_id, result, recovery):
        """Send a start whose outcome was never confirmed again, with the same launch number.

        Overnight 2026-10-23: two START requests timed out at the edge, the lab never queued them, and every poll said
        "waiting for worker acknowledgement", so the run stayed STARTING. The lab queues a start once per (assignment,
        device, recovery, launch) and ignores a repeat, so this never starts a second process."""
        previous = result[worker_id]
        try:
            value = self.start_worker(root, self.workers[worker_id], recovery, previous.get("launch", 0))
        except Exception:
            return False
        result[worker_id] = {
            "alive": value["alive"],
            "confirmed": True,
            "ready": value["ready"],
            **launched(previous.get("launch", 0)),
        }
        self._record_worker_block(root, worker_id, result[worker_id], value.get("events", []))
        return True

    def _restart_members(self, root, state):
        """
        A member whose worker is not running while the run goes on is started again once its device answers and is ON:
        it died (machine off, app killed, crash), gave up on an unreachable coordinator, was away at preparation, or
        left and was added back. Before, only preparation and a first JOIN started a worker, so such a member stayed
        idle until the end of the run.

        A restart is a new launch with its own number: the lab queues it as a new command and the device starts it in its
        own directory, never beside the old process, which is confirmed stopped first (here, and again on the device).
        A quarantined worker is never started again; a worker that keeps dying stops being restarted after MAX_LAUNCHES.
        """
        membership = read_json(root / "membership.json", {})
        members = membership.get("members", read_json(root / "config.json")["workerIds"])
        quarantined = read_json(self.root / "quarantine.json", {})
        blocked = read_json(root / "worker-blocks.json", {})
        result = dict(state.get("workerStates", {}))
        recovery = state.get("recoveryCount", 0)
        now = time.time()
        for worker_id in members:
            value = result.get(worker_id)
            key = (root.name, worker_id)
            stopped = value and value.get("alive") is False  # also one never started, or one that left
            if not stopped or not value.get("confirmed") or worker_id in quarantined or worker_id in blocked:
                self.retry_at.pop(key, None)
                continue
            if now < self.retry_at.get(key, 0):
                continue
            self.retry_at[key] = now + RESTART_SECONDS
            launch = 0 if value.get("notStarted") else value.get("launch", 0) + 1  # a never-started one has none yet
            if launch >= MAX_LAUNCHES and not value.get("retryPending"):
                self.retry_at[key] = float("inf")
                self.log(root, "worker_restart_limit", worker_id=worker_id, launch=launch)
                continue
            try:
                self.remote(self.workers[worker_id], {"action": "probe"})  # away, OFF or not approved: ask again later
            except Exception as error:
                # say why, once per reason: the lab's status tells away (503), OFF (409) and not in the run (403) apart
                reason = {
                    "error": type(error).__name__,
                    "httpStatus": error.code if isinstance(error, urllib.error.HTTPError) else None,
                }
                if self.deferred.get(key) != reason:
                    self.deferred[key] = reason
                    self.log(root, "worker_restart_deferred", worker_id=worker_id, launch=launch, **reason)
                continue
            self.deferred.pop(key, None)
            # a member added back after it left joins again; the timeline shows it as a join (finding 9)
            if value.get("left"):
                self.log(root, "worker_joined", worker_id=worker_id, launch=launch, rejoin=True)
            else:
                self.log(root, "worker_restarted", worker_id=worker_id, launch=launch)
            self._launch_worker(root, worker_id, result, recovery, launch)

    def _follow_membership(self, root, state):
        """Elastic membership (ADR-009): start the workers that joined at the last boundary, stop the ones that left.
        The runner decides membership and records it in the ledger; this only owns the worker processes."""
        membership = read_json(root / "membership.json", {})
        result = dict(state.get("workerStates", {}))
        recovery = state.get("recoveryCount", 0)
        for worker_id in membership.get("members", []):
            if worker_id not in result:
                self.log(root, "worker_joined", worker_id=worker_id)
                self._start_one(root, worker_id, result, recovery)
        for worker_id in membership.get("left", []):
            value = result.get(worker_id)
            if not value or value.get("notStarted") or value.get("left"):
                continue
            if value.get("confirmed") and not value.get("alive"):
                result[worker_id] = {**value, "left": True}  # already stopped (turned OFF): nothing to stop
            else:
                launch = value.get("launch", 0)
                try:
                    reply = self.remote(
                        self.workers[worker_id],
                        {"action": "stop", "runId": root.name + f"-r{recovery}", **launched(launch)},
                    )
                    result[worker_id] = {
                        "alive": reply["alive"],
                        "ready": reply.get("ready", False),
                        "confirmed": True,
                        **launched(launch),
                    }
                    if not reply["alive"]:
                        result[worker_id]["left"] = True  # the lab releases its GPU when it sees this
                except Exception:
                    result[worker_id] = {**value, "confirmed": False}
            if result[worker_id].get("left"):
                self.log(
                    root, "worker_left", worker_id=worker_id
                )  # once, when it is really out (it was logged per tick)
            self.save(root, workerStates=result)

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
                self._start_one(root, worker_id, result, state.get("recoveryCount", 0))
            self.save(root, workersLaunched=True, preparingAt=time.time())
        state = self.state(root)
        if state.get("workersLaunched") and runner.get("status") == "RUNNING":
            self._follow_membership(root, state)
            self._restart_members(root, self.state(root))
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
                    self.save(
                        root,
                        status="FAILED" if state.get("failureReason") else runner["status"],
                        completedAt=time.time(),
                        finalWeightsSha256=runner.get("final_weights_sha256"),
                        pauseCheckpoint=runner.get("pauseCheckpoint"),
                        failureReason=state.get("failureReason") or runner.get("failureReason"),
                    )
                    return
            self.save(
                root,
                status="CANCELLING"
                if runner["status"] == "CANCELLED"
                else "PAUSING"
                if runner["status"] == "PAUSED"
                else "DRAINING",
            )
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
            self.save(
                root, status="RECOVERING", recoveryCount=1, workersLaunched=False, workerStates={}, failureReason=None
            )
            self.log(root, "coordinator_recovery", recoveryCount=1)
            self.launch(root)
        else:
            self.save(
                root,
                status="CANCELLING"
                if (root / "cancel.flag").exists()
                else "PAUSING"
                if (root / "pause.flag").exists()
                else "RUNNING"
                if runner.get("status") == "RUNNING"
                else "STARTING",
            )

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
        result = {
            "state": self.state(root),
            "generations": [],
            "candidates": [],
            "attempts": [],
            "events": events(root / "lifecycle.jsonl") + events(root / "events.jsonl"),
            "artifacts": [],
        }
        if (root / "membership.json").exists():  # members now, left, refused: no credential is in this file
            result["membership"] = read_json(root / "membership.json")
        for path in root.glob("worker-*-r*.json"):
            # Worker configuration files also start with worker-; only collected event arrays belong here.
            worker_events = read_json(path, [])
            if isinstance(worker_events, list) and all(isinstance(event, dict) for event in worker_events):
                result["events"].extend(worker_events)
            else:
                result["monitoringPartial"] = True
        recipe = next((item["recipe"] for item in result["events"] if item.get("event") == "managed_start"), {})
        workload = recipe.get("workload", recipe.get("numerical", {}).get("workload", {}))
        contexts = {}
        usage_store, usage_candidates = None, {}
        delivery_faults = set()
        for event in result["events"]:
            usage = event.get("usage")
            delivery = usage.get("delivery") if isinstance(usage, dict) else None
            if (
                event.get("event") == "generation_done"
                and type(event.get("generation")) is int
                and isinstance(delivery, dict)
                and any(type(delivery.get(key)) is int and delivery[key] > 0 for key in ("errors", "dropped"))
            ):
                delivery_faults.add(event["generation"])
        if (root / "usage.sqlite").is_file():
            try:
                from heteroes.v3.usage import UsageStore

                usage_store = UsageStore(root / "usage.sqlite", create=False)
                usage_candidates = usage_store.candidates()
            except Exception:
                result["usageSummary"] = {"partial": True, "unavailable": True}
                usage_store = None
        db_path = root / "ledger.sqlite"
        checkpoint = result["state"].get("finalWeightsSha256")
        weights = data_root(root) / "weights"
        if db_path.exists():
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                db.execute("BEGIN")  # consistent projection, never mutate the runtime ledger
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='generation_context'").fetchone():
                    contexts = {
                        r["generation"]: json.loads(r["body"])
                        for r in db.execute("SELECT generation,body FROM generation_context")
                    }
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='audit'").fetchone():
                    total, mismatches = db.execute("SELECT count(*),coalesce(sum(matched=0),0) FROM audit").fetchone()
                    result["auditSummary"] = {
                        "completed": total,
                        # chosen for re-execution, from each generation's summary (ADR-009); less completed = timed out
                        "selected": sum(
                            event.get("audits", {}).get("selected", 0)
                            for event in result["events"]
                            if event.get("event") == "generation_done" and isinstance(event.get("audits"), dict)
                        ),
                        "mismatches": mismatches,
                        "quarantinedWorkers": [
                            dict(r) for r in db.execute("SELECT worker_id,reason FROM quarantine ORDER BY worker_id")
                        ],
                    }
                for gen in db.execute(
                    "SELECT g.*, u.child_weights_sha256, u.applied_at FROM generation g LEFT JOIN generation_update u USING(experiment_id,generation) ORDER BY g.generation"
                ):
                    if gen["applied_at"] and (weights / (gen["child_weights_sha256"] + ".bin")).is_file():
                        checkpoint = gen["child_weights_sha256"]
                    number = gen["generation"]
                    generation_id = f"{run_id}.g{number}"
                    rewards = [
                        row[0]
                        for row in db.execute(
                            "SELECT reward FROM result JOIN candidate USING(candidate_id) WHERE generation=?", (number,)
                        )
                    ]
                    count = db.execute("SELECT count(*) FROM candidate WHERE generation=?", (number,)).fetchone()[0]
                    row = {
                        "experimentId": run_id,
                        "generationId": generation_id,
                        "modelVersion": gen["parent_weights_sha256"],
                        "status": "COMPLETED"
                        if gen["applied_at"]
                        else result["state"]["status"]
                        if result["state"].get("status") in ("CANCELLED", "FAILED")
                        else "RUNNING",
                        "candidateCount": count,
                        "committedCandidateCount": len(rewards),
                        "completedAt": iso(gen["applied_at"]),
                    }
                    row["startedAt"] = next(
                        (
                            iso(item["t"])
                            for item in result["events"]
                            if item.get("event") == "generation_open" and item.get("generation") == number
                        ),
                        None,
                    )
                    if rewards:
                        row.update(rewardMean=sum(rewards) / len(rewards), rewardBest=max(rewards))
                    if number in contexts:
                        row["generationContext"] = contexts[number]
                    validation = read_json(root / f"validation-{number}.json")
                    if validation and "meanReward" in validation:
                        row["validationReward"] = validation["meanReward"]
                    if usage_store is not None:
                        try:
                            audit_count = db.execute(
                                "SELECT count(*) FROM audit JOIN candidate USING(candidate_id) WHERE generation=?",
                                (number,),
                            ).fetchone()[0]
                            row["usage"] = usage_store.summary(
                                number,
                                expected_candidates=count,
                                expected_audits=audit_count,
                                expected_updates=int(bool(gen["applied_at"])),
                            )
                            row["usage"]["partial"] |= number in delivery_faults
                        except Exception:
                            row["usage"] = {"partial": True, "unavailable": True}
                    result["generations"].append(row)
                for c in db.execute(
                    "SELECT c.*,g.recipe_hash,g.parent_weights_sha256,r.reward FROM candidate c JOIN generation g USING(experiment_id,generation) LEFT JOIN result r USING(candidate_id)"
                ):
                    attempts = list(
                        db.execute(
                            "SELECT attempt_number,worker_id,leased_at,deadline,ended_at,failure_kind FROM attempt WHERE candidate_id=? ORDER BY attempt_number",
                            (c["candidate_id"],),
                        )
                    )
                    # The UI ID is separate from canonical descriptor identity, which stays in the ledger.
                    cid = f"{run_id}.g{c['generation']}.c{c['candidate_index']}"
                    item = {
                        "experimentId": run_id,
                        "generationId": f"{run_id}.g{c['generation']}",
                        "candidateId": cid,
                        "modelVersion": c["parent_weights_sha256"],
                        "seed": str(c["seed"]),
                        "noiseRecipeHash": c["recipe_hash"],
                        "generationConfigHash": workload.get("generation_config_sha256"),
                        "batchIds": [workload["hash"]] if workload.get("hash") else [],
                        "status": c["state"],
                    }
                    if c["reward"] is not None:
                        item["reward"] = c["reward"]
                    if c["candidate_id"] in usage_candidates:
                        item["usage"] = usage_candidates[c["candidate_id"]]
                    if c["generation"] in contexts:
                        item["batchIds"] = [contexts[c["generation"]]["batchHash"]]
                        item["effectiveSigma"] = contexts[c["generation"]]["sigmaFloat32"]
                    for a in attempts:
                        aid = cid + f".a{a['attempt_number']}"
                        success = db.execute(
                            "SELECT committed_at FROM result WHERE candidate_id=? AND attempt_number=?",
                            (c["candidate_id"], a["attempt_number"]),
                        ).fetchone()
                        expired = not a["ended_at"] and a["deadline"] < time.time()
                        result["attempts"].append(
                            {
                                "experimentId": run_id,
                                "generationId": item["generationId"],
                                "candidateId": cid,
                                "attemptId": aid,
                                "workerId": a["worker_id"],
                                "modelVersion": c["parent_weights_sha256"],
                                "status": "SUCCEEDED"
                                if success
                                else "FAILED"
                                if a["failure_kind"] or expired
                                else "RUNNING",
                                "startedAt": iso(a["leased_at"]),
                                "completedAt": iso(success[0] if success else a["ended_at"]),
                                "errorType": a["failure_kind"] or ("LEASE_EXPIRED" if expired else None),
                            }
                        )
                        item.update(attemptId=aid, workerId=a["worker_id"], leaseDeadline=iso(a["deadline"]))
                    result["candidates"].append(item)
        for event in result["events"]:
            if event.get("candidate_id"):
                event["uiCandidateId"] = event["candidate_id"].replace("/", ".")
        allowed = [
            root / "config.json",
            root / "events.jsonl",
            root / "lifecycle.jsonl",
            *root.glob("summary-*.json"),
            *root.glob("validation-*.json"),
            *root.glob("study-*.json"),
        ]
        result["studyMetrics"] = read_json(root / "study-metrics.json")
        result["checkpointSha256"] = checkpoint
        if checkpoint:
            allowed.append(weights / (checkpoint + ".bin"))
        for path in allowed:
            if path.is_file():
                name = path.name
                result["artifacts"].append(
                    {
                        "artifactId": run_id + "." + name,
                        "experimentId": run_id,
                        "name": name,
                        "path": name,
                        "type": "CHECKPOINT"
                        if name.endswith(".bin")
                        else "CONFIG"
                        if name == "config.json"
                        else "EVALUATION_RESULTS",
                        "status": "READY",
                        "sizeBytes": path.stat().st_size,
                        "createdAt": iso(path.stat().st_mtime),
                    }
                )
        if usage_store is not None:
            try:
                result["usageSummary"] = usage_store.summary(
                    expected_candidates=sum(g["candidateCount"] for g in result["generations"]),
                    expected_audits=result.get("auditSummary", {}).get("completed", 0),
                    expected_updates=sum(g["status"] == "COMPLETED" for g in result["generations"]),
                )
                result["usageSummary"]["partial"] |= bool(delivery_faults)
            except Exception:
                result["usageSummary"] = {"partial": True, "unavailable": True}
        return result

    @abstractmethod
    def launch(self, root):
        """Launch the coordinator only with the current agent boot's opt-in."""

    @abstractmethod
    def remote(self, worker, request):
        """Relay a fixed worker lifecycle command through the Lab Server."""

    @abstractmethod
    def start_worker(self, root, worker, recovery, launch=0):
        """Start an assigned worker with the agent's fenced compute grant; `launch` numbers its restarts."""
