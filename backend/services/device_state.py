"""DeviceStateService business operations behind the Store facade."""

import json
from ..policies import read_setting, set_disabled_workers
from ..repositories.device_state import DeviceStateRepository as repository


class DeviceStateService:
    def __init__(self, store):
        self.store = store

    def ensure_workers(self, ids):
        with self.store.db() as db:
            initialized = bool(repository.ensure_workers_select_settings(db, ()).fetchone())
            creator = repository.ensure_workers_select_workspaces(db, ()).fetchone()[0]
            disabled = self.store.disabled_workers(db)
            for wid in ids:
                if not repository.ensure_workers_select_worker_assignments(db, (wid,)).fetchone():
                    repository.ensure_workers_insert_worker_assignments(
                        db, (wid, creator, None if initialized else "lab")
                    )
                    if initialized:
                        disabled.add(wid)
            set_disabled_workers(db, disabled)
            repository.ensure_workers_insert_settings(db, ("workersInitialized", "true"))
        if self.store.last_error == "WorkerConfigurationUnavailable":
            self.store.last_error = None

    def assignments(self, workspace_id, include_disabled=False):
        with self.store.db() as db:
            disabled = self.store.disabled_workers(db)
            return [
                r[0]
                for r in repository.assignments_select_worker_assignments(db, (workspace_id,))
                if include_disabled or r[0] not in disabled
            ]

    def disabled_workers(self, db):
        return set(read_setting(db, "disabledWorkers", []))

    def device_names(self):
        """{worker id: the name its owner gave the device}, for screens that would otherwise show the raw id."""
        with self.store.db() as db:
            return {r[0]: r[1] for r in repository.device_names_select_devices(db, ())}

    def device_identities(self):
        with self.store.db() as db:
            return {
                row["worker_id"]: {
                    "name": row["name"],
                    "gpuName": json.loads(row["self_test"]).get("gpuName"),
                    "gpuUUID": json.loads(row["self_test"]).get("gpuUUID"),
                    "gpuIndex": json.loads(row["self_test"]).get("gpuIndex"),
                    "source": "current",
                }
                for row in repository.device_identities_select_devices(db, ())
            }
