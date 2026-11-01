"""SQLite product state. Runtime ledgers remain owned by device agents."""

from .migrations import initialize_product_schema
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading

from argon2 import PasswordHasher
from .migrations import initialize_workspace_extras, migrate

from .services.accounts import AccountService
from .services.device_state import DeviceStateService
from .services.scheduling import SchedulingService
from .services.experiment_state import ExperimentStateService
from .services.workspaces import WorkspaceStateService
from .core.clock import now
from .core.constants import ACTIVE as ACTIVE, TERMINAL as TERMINAL


class Store:
    def __init__(self, path, passwords, runtime):
        self.path, self.runtime = str(path), runtime
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self.hasher = PasswordHasher()
        self.accounts = AccountService(self)
        self.device_state = DeviceStateService(self)
        self.scheduling = SchedulingService(self)
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
        return self.device_state.ensure_workers(ids=ids)

    def profile(self, user_id):
        return self.accounts.profile(user_id)

    def workspaces(self, user_id):
        return self.workspace_state.workspaces(user_id=user_id)

    def assignments(self, workspace_id, include_disabled=False):
        return self.device_state.assignments(workspace_id=workspace_id, include_disabled=include_disabled)

    def disabled_workers(self, db):
        return self.device_state.disabled_workers(db=db)

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
        return self.device_state.device_names()

    def device_identities(self):
        return self.device_state.device_identities()

    def snapshot(self, run_id):
        return self.experiments.snapshot(run_id=run_id)

    def dispatch_once(self):
        return self.scheduling.dispatch_once()

    def _dispatch_once(self):
        return self.scheduling._dispatch_once()

    def _dispatch_run(self, active):
        return self.scheduling._dispatch_run(active=active)

    def dispatch(self, stop):
        return self.scheduling.dispatch(stop=stop)  # errors never become fabricated success/rewards
