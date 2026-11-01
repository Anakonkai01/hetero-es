"""SQLite product state. Runtime ledgers remain owned by device agents."""

from .migrations import initialize_product_schema
from .policies import dispatch_held, read_setting, set_disabled_workers
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading

from argon2 import PasswordHasher
from .errors import RuntimeRejected
from .migrations import initialize_workspace_extras, migrate

from .constants import ACTIVE, TERMINAL, V3_CODE_KEYS, V3_KEYS, V3_UPDATE_KEYS
from .services.accounts import AccountService
from .services.experiment_state import ExperimentStateService
from .services.workspaces import WorkspaceStateService
from .core.clock import now


class Store:
    def __init__(self, path, passwords, runtime):
        self.path, self.runtime = str(path), runtime
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.hasher = PasswordHasher()
        self.accounts = AccountService(self)
        self.experiments = ExperimentStateService(self)
        self.workspace_state = WorkspaceStateService(self)
        self.last_error = None
        with self.db() as db:
            initialize_product_schema(db)
            for name, password in passwords.items():
                profile = {"userId": name, "username": name, "displayName": name.title(), "canCreateWorkspace": False}
                # Bootstrap secrets seed an empty installation only. A renamed
                # or removed account must not be recreated on every restart.
                if db.execute("PRAGMA user_version").fetchone()[0] == 0:
                    db.execute(
                        "INSERT OR IGNORE INTO users VALUES (?,?,?)",
                        (name, self.hasher.hash(password), json.dumps(profile)),
                    )
            db.commit()
            migrate(db)
            initialize_workspace_extras(db)
        os.chmod(path, 0o600)
        runtime.attach_store(self)
        try:
            self.ensure_workers(runtime.capabilities()["workerIds"])
        except Exception:
            self.last_error = "WorkerConfigurationUnavailable"

    @contextmanager
    def db(self):
        with self.lock:
            connection = sqlite3.connect(self.path, timeout=20)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.close()

    def audit(self, db, actor, action, target, workspace_id=None):
        db.execute(
            "INSERT INTO audit(actor,action,target,created,workspace_id) VALUES (?,?,?,?,?)",
            (actor, action, target, now(), workspace_id),
        )

    def ensure_workers(self, ids):
        with self.db() as db:
            initialized = bool(db.execute('SELECT value FROM settings WHERE key="workersInitialized"').fetchone())
            creator = db.execute('SELECT creator FROM workspaces WHERE id="lab"').fetchone()[0]
            disabled = self.disabled_workers(db)
            for wid in ids:
                if not db.execute("SELECT 1 FROM worker_assignments WHERE worker_id=?", (wid,)).fetchone():
                    db.execute(
                        "INSERT INTO worker_assignments VALUES (?,?,?)", (wid, creator, None if initialized else "lab")
                    )
                    if initialized:
                        disabled.add(wid)
            set_disabled_workers(db, disabled)
            db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", ("workersInitialized", "true"))
        if self.last_error == "WorkerConfigurationUnavailable":
            self.last_error = None

    def profile(self, user_id):
        return self.accounts.profile(user_id)

    def workspaces(self, user_id):
        return self.workspace_state.workspaces(user_id=user_id)

    def assignments(self, workspace_id, include_disabled=False):
        with self.db() as db:
            disabled = self.disabled_workers(db)
            return [
                r[0]
                for r in db.execute("SELECT worker_id FROM worker_assignments WHERE workspace_id=?", (workspace_id,))
                if include_disabled or r[0] not in disabled
            ]

    def disabled_workers(self, db):
        return set(read_setting(db, "disabledWorkers", []))

    def cancel_selected(self, db, worker_id, *, include_queued=True, keep=()):
        return self.experiments.cancel_selected(db=db, worker_id=worker_id, include_queued=include_queued, keep=keep)

    def cancel_owned(self, db, owner, workspace_id=None):
        return self.experiments.cancel_owned(db=db, owner=owner, workspace_id=workspace_id)

    def eligibility(self, db, body, workers=None):
        return self.experiments.eligibility(db=db, body=body, workers=workers)

    def get(self, run_id):
        return self.experiments.get(run_id=run_id)

    def list(self):
        return self.experiments.list()

    def save(self, db, body):
        return self.experiments.save(db=db, body=body)

    def create(self, owner, config, workspace_id="lab"):
        return self.experiments.create(owner=owner, config=config, workspace_id=workspace_id)

    def device_names(self):
        """{worker id: the name its owner gave the device}, for screens that would otherwise show the raw id."""
        with self.db() as db:
            return {r[0]: r[1] for r in db.execute("SELECT worker_id,name FROM devices WHERE name<>''")}

    def device_identities(self):
        with self.db() as db:
            return {
                row["worker_id"]: {
                    "name": row["name"],
                    "gpuName": json.loads(row["self_test"]).get("gpuName"),
                    "gpuUUID": json.loads(row["self_test"]).get("gpuUUID"),
                    "gpuIndex": json.loads(row["self_test"]).get("gpuIndex"),
                    "source": "current",
                }
                for row in db.execute("SELECT worker_id,name,self_test FROM devices")
            }

    def snapshot(self, run_id):
        return self.experiments.snapshot(run_id=run_id)

    def dispatch_once(self):
        with self.operation_lock:
            self._dispatch_once()

    def _dispatch_once(self):
        """Always reconcile admitted work; hold only admission of new queued work."""
        errors = []
        for active in [body for body in self.list() if body["status"] in ACTIVE]:
            try:
                self._dispatch_run(active)
                with self.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    self.runtime.auto_join(db, self.get(active["experimentId"]))  # it checks allowJoin itself
            except Exception as error:
                errors.append(type(error).__name__)
        with self.db() as db:
            queued = [row[0] for row in db.execute("SELECT run_id FROM queue ORDER BY sequence")]
        for run_id in queued:
            with self.db() as db:
                # Recheck under the same lock as the queued-to-STARTING claim.
                # An operator can hold admission while reconciliation is running.
                if dispatch_held(db):
                    break
                active = self.get(run_id)
                if not active or active["status"] != "QUEUED":
                    continue
                if reason := self.eligibility(db, active):
                    active.update(status="CANCELLED", cancelRequested=True, completedAt=now(), failureReason=reason)
                    self.save(db, active)
                    db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
                    self.audit(db, "system", "QUEUE_ACCESS_REVOKED", run_id, active["workspaceId"])
                    continue
                if waiting := self.runtime.waiting_reason(active):
                    active["waitingReason"] = waiting
                    self.save(db, active)
                    continue
                active.pop("waitingReason", None)
                active.update(status="STARTING", startedAt=now())
                self.save(db, active)
            # Reserve before considering the next job; retry this frozen run on
            # lost responses, and keep unrelated jobs progressing through errors.
            try:
                self._dispatch_run(active)
            except Exception as error:
                errors.append(type(error).__name__)
        self.last_error = errors[0] if errors else None

    def _dispatch_run(self, active):
        run_id = active["experimentId"]
        # Submission can succeed while its response is lost. The runtime rejects
        # changes to an existing run and accepts retries of this exact payload.
        config = {
            "runId": run_id,
            "workerIds": active["workerIds"],
            "workload": active["task"],
            **{
                key: active[key]
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
        config.update(
            coordinatorDeviceId=active["coordinatorDeviceId"],
            backupPolicy=active.get("backupPolicy", {"interval": 1, "retain": 3}),
        )
        if active.get("recipeVersion") in (2, 3):
            config.update(
                {
                    key: active[key]
                    for key in (
                        "recipeVersion",
                        "modelManifest",
                        "modelSource",
                        "datasetObjectSha256",
                        "datasetIdentity",
                        "batchSize",
                        "batchSeed",
                        "sigmaSchedule",
                        "sigmaMinimum",
                        "maxNewTokens",
                        "validationInterval",
                    )
                }
            )
        if "datasetSplitObjects" in active:  # a file-backed dataset (format 3)
            config["datasetSplitObjects"] = active["datasetSplitObjects"]
        if active.get("recipeVersion") == 3:
            config.update({key: active[key] for key in V3_KEYS})
            config.update({key: active[key] for key in (*V3_UPDATE_KEYS, *V3_CODE_KEYS) if key in active})
        try:
            self.runtime.submit(config)
        except RuntimeRejected as error:
            with self.db() as db:
                body = self.get(run_id)
                body.update(status="FAILED", failureReason=str(error), completedAt=now())
                self.save(db, body)
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            return
        current = self.get(run_id)
        if current.get("cancelRequested"):
            self.runtime.cancel(run_id)
        elif current.get("pauseRequested"):
            self.runtime.pause(run_id)
        snapshot = self.runtime.snapshot(run_id)
        with self.db() as db:
            body = self.get(run_id)
            state = snapshot["state"]
            body["status"] = state["status"]
            if body.get("cancelRequested") and body["status"] == "PAUSED":
                body["status"] = "CANCELLED"
            if (
                body.get("pauseRequested")
                and not body.get("cancelRequested")
                and body["status"] in ("STARTING", "RUNNING")
            ):
                body["status"] = "PAUSING"
            if state.get("pauseCheckpoint"):
                body["pauseCheckpoint"] = state["pauseCheckpoint"]
            if body["status"] == "PAUSED":
                body["pausedAt"] = now()
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            if "cloudSync" in snapshot:
                previous = body.get("cloudSync", {})
                incoming = snapshot["cloudSync"]
                body["cloudSync"] = {**incoming}
                if previous.get("lastCloudGeneration", -1) > incoming.get("lastCloudGeneration", -1):
                    body["cloudSync"].update(
                        {k: previous[k] for k in ("lastCloudGeneration", "pointId") if k in previous}
                    )
            generations = snapshot["generations"]
            complete = [item for item in generations if item["status"] == "COMPLETED"]
            body["completedGenerations"] = snapshot.get("completedGenerationCount", len(complete))
            body["monitoringPartial"] = bool(snapshot.get("monitoringPartial"))
            body["workerBlocks"] = {
                worker: {"reason": value["stopReason"], "blockedAt": value.get("blockedAt")}
                for worker, value in state.get("workerStates", {}).items()
                if value.get("stopReason")
            }
            if snapshot.get("auditSummary") is not None:
                body["auditSummary"] = snapshot["auditSummary"]
            if isinstance(
                snapshot.get("membership"), dict
            ):  # who works on it now, as its coordinator recorded (ADR-009)
                body["membership"] = {
                    key: snapshot["membership"].get(key, []) for key in ("members", "left", "refused")
                } | {"generation": snapshot["membership"].get("generation")}
            if snapshot.get("usageSummary") is not None:
                body["usageSummary"] = snapshot["usageSummary"]
            if snapshot.get("studyMetrics"):
                body["studyMetrics"] = snapshot["studyMetrics"]
                best = snapshot["studyMetrics"].get("best") or {}
                if "validationAccuracy" in best:
                    body["validationScore"] = best["validationAccuracy"]
                if "validationReward" in best:
                    body["validationScore"] = best["validationReward"]
                if "testReward" in snapshot["studyMetrics"]:
                    body["testScore"] = snapshot["studyMetrics"]["testReward"]
                if "testAccuracy" in snapshot["studyMetrics"]:
                    body["testScore"] = snapshot["studyMetrics"]["testAccuracy"]
            latest = snapshot.get("latestGeneration") or (generations[-1] if generations else None)
            if latest:
                body["currentGenerationId"] = latest["generationId"]
                body["committedCandidateCount"] = latest["committedCandidateCount"]
                body["modelVersion"] = latest["modelVersion"]
            if "failureReason" in state:
                body["failureReason"] = state["failureReason"]
            if state.get("finalWeightsSha256"):
                body["modelVersion"] = state["finalWeightsSha256"]
            elif body["status"] in TERMINAL and snapshot.get("checkpointSha256"):
                body["modelVersion"] = snapshot["checkpointSha256"]
            if body["status"] in TERMINAL:
                body["completedAt"] = now()
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            self.save(db, body)
            db.execute("UPDATE experiments SET snapshot=? WHERE id=?", (json.dumps(snapshot, allow_nan=False), run_id))

    def dispatch(self, stop):
        while not stop.wait(1):
            try:
                self.dispatch_once()
            except Exception as error:
                self.last_error = type(error).__name__  # errors never become fabricated success/rewards
