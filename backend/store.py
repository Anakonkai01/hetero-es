"""SQLite product state. Runtime ledgers are reachable only through the control API."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from argon2 import PasswordHasher
from .runtime import RuntimeRejected

ACTIVE = {"STARTING", "RUNNING", "CANCELLING", "RECOVERING", "DRAINING"}
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path, passwords, runtime):
        self.path, self.runtime = str(path), runtime
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.hasher = PasswordHasher()
        self.last_error = None
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, hash TEXT NOT NULL, profile TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, snapshot TEXT);
                CREATE TABLE IF NOT EXISTS queue (sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, created TEXT);
            """)
            for name, password in passwords.items():
                profile = {"userId": name, "username": name, "displayName": name.title(), "canCreateWorkspace": False}
                db.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (name, self.hasher.hash(password), json.dumps(profile)))
        os.chmod(path, 0o600)

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

    def audit(self, db, actor, action, target):
        db.execute("INSERT INTO audit(actor,action,target,created) VALUES (?,?,?,?)", (actor, action, target, now()))

    def get(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT body FROM experiments WHERE id=?", (run_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def list(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM experiments ORDER BY rowid")]

    def save(self, db, body):
        db.execute("UPDATE experiments SET body=? WHERE id=?", (json.dumps(body, allow_nan=False), body["experimentId"]))

    def create(self, owner, config):
        run_id = uuid.uuid4().hex
        digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        body = {**config, "experimentId": run_id, "workspaceId": "lab", "ownerUserId": owner, "status": "DRAFT",
                "cancelRequested": False, "modelVersion": "7ae557604adf67be50417f59c2c2f167def9a775",
                "configHash": digest, "createdAt": now(), "completedGenerations": 0}
        with self.db() as db:
            db.execute("INSERT INTO experiments VALUES (?,?,?,NULL)", (run_id, owner, json.dumps(body)))
            self.audit(db, owner, "CREATE", run_id)
        return body

    def snapshot(self, run_id):
        with self.db() as db:
            row = db.execute("SELECT snapshot FROM experiments WHERE id=?", (run_id,)).fetchone()
            return json.loads(row[0]) if row and row[0] else {"generations": [], "candidates": [], "attempts": [], "events": [], "artifacts": []}

    def dispatch_once(self):
        # Only one dispatcher in the supported one-process deployment. Durable state
        # is claimed before the RPC; retry uses the same run ID and frozen config.
        with self.db() as db:
            active = next((body for body in self.list() if body["status"] in ACTIVE), None)
            if active is None:
                row = db.execute("SELECT run_id FROM queue JOIN experiments ON experiments.id=queue.run_id ORDER BY sequence LIMIT 1").fetchone()
                if row:
                    active = self.get(row[0])
                    if active["status"] != "QUEUED":
                        db.execute("DELETE FROM queue WHERE run_id=?", (row[0],))
                        return
                    active.update(status="STARTING", startedAt=now())
                    self.save(db, active)
        if active is None:
            return
        run_id = active["experimentId"]
        # Submission can succeed while its response is lost. The runtime rejects
        # changes to an existing run and accepts retries of this exact payload.
        config = {"runId": run_id, "workerIds": active["workerIds"], "workload": active["task"],
                  **{key: active[key] for key in ("candidatesPerGeneration", "maxGenerations", "alpha", "sigma", "decodeEngine", "schedulerPolicy", "syncMode")}}
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
        snapshot = self.runtime.snapshot(run_id)
        with self.db() as db:
            body = self.get(run_id)
            state = snapshot["state"]
            body["status"] = state["status"]
            generations = snapshot["generations"]
            complete = [item for item in generations if item["status"] == "COMPLETED"]
            body["completedGenerations"] = len(complete)
            if generations:
                body["currentGenerationId"] = generations[-1]["generationId"]
                body["committedCandidateCount"] = generations[-1]["committedCandidateCount"]
                body["modelVersion"] = generations[-1]["modelVersion"]
            if state.get("failureReason"):
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
        self.last_error = None
        # The next tick claims the next queued run inside the same lock as cancel.

    def dispatch(self, stop):
        while not stop.wait(1):
            try:
                self.dispatch_once()
            except Exception as error:
                self.last_error = type(error).__name__  # errors never become fabricated success/rewards
