"""Experiment state and admission business rules, behind the Store facade."""

import hashlib
import json
import uuid
from ..core.clock import now
from ..constants import TERMINAL, REVISION
from ..experiment_view import experiment_view
from ..repositories.experiments import ExperimentsRepository as repository


class ExperimentStateService:
    def __init__(self, store):
        self.store = store

    def cancel_selected(self, db, worker_id, *, include_queued=True, keep=()):
        for row in repository.state_cancel_selected_select_experiments(db, ()).fetchall():
            b = json.loads(row[0])
            if b["experimentId"] in keep:
                continue
            coordinator = b.get("coordinatorDeviceId")
            coordinator_alias = None
            if coordinator:
                row = repository.state_cancel_selected_select_devices(db, (coordinator,)).fetchone()
                coordinator_alias = row[0] if row else None
            if worker_id not in set(b["workerIds"]) | {coordinator_alias} or b["status"] in TERMINAL | {
                "DRAFT",
                "PAUSED",
            }:
                continue
            if not include_queued and b["status"] == "QUEUED":
                continue
            b["cancelRequested"] = True
            if b["status"] in ("QUEUED", "PAUSED"):
                b.update(status="CANCELLED", completedAt=now(), failureReason="GPU contribution was disabled")
                repository.state_cancel_selected_delete_queue(db, (b["experimentId"],))
            else:
                b["status"] = "CANCELLING"
            self.store.save(db, b)
            self.store.audit(db, "system", "GPU_CONTRIBUTION_DISABLED", b["experimentId"], b["workspaceId"])

    def cancel_owned(self, db, owner, workspace_id=None):
        for row in repository.state_cancel_owned_select_experiments(db, (owner,)).fetchall():
            body = json.loads(row[0])
            if workspace_id and body["workspaceId"] != workspace_id:
                continue
            if body["status"] in TERMINAL | {"DRAFT"}:
                continue
            body["cancelRequested"] = True
            if body["status"] in ("QUEUED", "PAUSED"):
                body.update(status="CANCELLED", completedAt=now(), failureReason="Resource access revoked")
                repository.state_cancel_owned_delete_queue(db, (body["experimentId"],))
            else:
                body["status"] = "CANCELLING"
            self.store.save(db, body)
            self.store.audit(db, "system", "ACCESS_REVOKED", body["experimentId"], body["workspaceId"])

    def eligibility(self, db, body, workers=None):
        row = repository.state_eligibility_select_users(db, (body["ownerUserId"],)).fetchone()
        if not row or json.loads(row[0])["accountStatus"] != "ACTIVE":
            return "Owner account is not active"
        if not repository.state_eligibility_select_memberships(
            db, (body["workspaceId"], body["ownerUserId"])
        ).fetchone():
            return "Workspace membership was revoked"
        ids = {r[0] for r in repository.state_eligibility_select_worker_assignments(db, (body["workspaceId"],))}
        if workers is None:
            workers = self.store.runtime.intended_members(db, body["experimentId"], body["workerIds"])
        if not set(workers) <= ids - self.store.disabled_workers(db):
            return "Selected GPU assignment changed before launch"
        co = repository.state_eligibility_select_devices(db, (body.get("coordinatorDeviceId"),)).fetchone()
        if not co or co["status"] != "APPROVED" or co["worker_id"] not in ids - self.store.disabled_workers(db):
            return "Coordinator approval or workspace assignment changed"
        chosen = repository.state_eligibility_select_devices_2(db, workers, workers=workers).fetchall()
        if len(chosen) != len(workers) or any(
            (
                d["status"] != "APPROVED" or self.store.profile(d["owner"])["accountStatus"] != "ACTIVE"
                for d in [co, *chosen]
            )
        ):
            return "Device owner or approval was revoked"
        return None

    def get(self, run_id):
        with self.store.db() as db:
            row = repository.state_get_select_experiments(db, (run_id,)).fetchone()
            return experiment_view(json.loads(row[0]), json.loads(row[1]) if row[1] else None) if row else None

    def list(self):
        with self.store.db() as db:
            return [
                experiment_view(json.loads(row[0]), json.loads(row[1]) if row[1] else None)
                for row in repository.state_list_select_experiments(db, ())
            ]

    def save(self, db, body):
        repository.state_save_update_experiments(db, (json.dumps(body, allow_nan=False), body["experimentId"]))

    def create(self, owner, config, workspace_id="lab"):
        run_id = uuid.uuid4().hex
        digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        body = {
            **config,
            "experimentId": run_id,
            "workspaceId": workspace_id,
            "ownerUserId": owner,
            "status": "DRAFT",
            "cancelRequested": False,
            "modelVersion": config.get("modelManifest", {}).get("revision", REVISION),
            "configHash": digest,
            "createdAt": now(),
            "completedGenerations": 0,
        }
        with self.store.db() as db:
            repository.state_create_insert_experiments(db, (run_id, owner, json.dumps(body)))
            self.store.audit(db, owner, "CREATE", run_id, workspace_id)
            for entry in config.get("pythonCode", []):
                target = f"{run_id}:{entry['role']}:{entry['codeSha256']}"
                self.store.audit(db, owner, "PYTHON_CODE_FROZEN", target, workspace_id)
        return body

    def snapshot(self, run_id):
        with self.store.db() as db:
            row = repository.state_snapshot_select_experiments(db, (run_id,)).fetchone()
            return (
                json.loads(row[0])
                if row and row[0]
                else {"generations": [], "candidates": [], "attempts": [], "events": [], "artifacts": []}
            )
