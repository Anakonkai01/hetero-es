"""Experiments business operations; HTTP responses stay in api/."""

from backend.core.errors import RuntimeRejected
from backend.core.request_models import BackupPolicy, Configuration, MembershipRequest
from .policies import dispatch_held
import hashlib
import json
import secrets
from ..core.constants import TERMINAL
from ..core.clock import now
from backend.core.constants import REVISION
from .timeline import build_timeline
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.experiments import ExperimentsRepository as repository
from ..db.transactions import begin_write


def operations(store, runtime, scoped, visible, authorized, validate):
    def experiments(*, current):
        return visible(current)

    def create(body: Configuration, *, current):
        with store.lock:
            return store.create(current["userId"], validate(body, current), current["workspaceId"])

    def experiment(run_id: str, *, current):
        return authorized(run_id, current)

    def run_timeline(run_id: str, *, current):
        return build_timeline(authorized(run_id, current), store.snapshot(run_id), names=store.device_identities())

    def edit(run_id: str, request: dict, *, current):
        with store.db() as db:
            old = authorized(run_id, current)
            if old["status"] != "DRAFT":
                raise ServiceError(409, "Submitted configuration is immutable")
            try:
                body = validate(Configuration(**request), current)
            except ValueError:
                raise ServiceError(422, "Invalid configuration") from None
            digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for key in set(Configuration.model_fields) | {
                "modelManifest",
                "modelSource",
                "datasetObjectSha256",
                "datasetIdentity",
            }:
                old.pop(key, None)
            old.update(**body, configHash=digest, modelVersion=body.get("modelManifest", {}).get("revision", REVISION))
            store.save(db, old)
            store.audit(db, current["userId"], "EDIT", run_id, current["workspaceId"])
            return old

    def submit(run_id: str, *, current):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] == "DRAFT":
                if dispatch_held(db):
                    raise ServiceError(409, "Submissions are held for maintenance or restored deployment review")
                if reason := store.eligibility(db, body):
                    raise ServiceError(409, reason)
                body["status"] = "QUEUED"
                repository.submit_insert_queue(db, (run_id,))
                store.save(db, body)
                store.audit(db, current["userId"], "SUBMIT", run_id, current["workspaceId"])
            elif body["status"] in TERMINAL:
                raise ServiceError(409, "Experiment already finished")
            return body

    def cancel(run_id: str, *, current):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] in TERMINAL:
                return body
            body["cancelRequested"] = True
            if body["status"] in ("DRAFT", "QUEUED", "PAUSED"):
                body.update(status="CANCELLED", completedAt=now())
                repository.cancel_delete_queue(db, (run_id,))
            else:
                body["status"] = "CANCELLING"
            store.save(db, body)
            store.audit(db, current["userId"], "CANCEL", run_id, current["workspaceId"])
            return body

    def archive(run_id: str, *, current):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] not in TERMINAL | {"DRAFT"}:
                raise ServiceError(409, "Cancel and wait for the experiment to finish before archiving")
            body["archivedAt"] = now()
            store.save(db, body)
            store.audit(db, current["userId"], "ARCHIVE", run_id, current["workspaceId"])
        return None

    def pause(run_id: str, *, current):
        with store.db() as db:
            begin_write(db)
            body = authorized(run_id, current)
            if body["status"] == "PAUSED":
                return body
            if body.get("cancelRequested") or body["status"] not in ("STARTING", "RUNNING", "PAUSING"):
                raise ServiceError(409, "Pause requires a running experiment")
            runtime.require_command(db, body["coordinatorDeviceId"], "PAUSE_ASSIGNMENT")
            runtime.pause(run_id, db=db)
            body.update(pauseRequested=True, status="PAUSING")
            store.save(db, body)
            store.audit(db, current["userId"], "PAUSE_REQUESTED", run_id, body["workspaceId"])
        return body

    def resume(run_id: str, *, current):
        with store.db() as db:
            begin_write(db)
            body = authorized(run_id, current)
            if body.get("resumeRequested") and body["status"] in ("QUEUED", "STARTING"):
                return body
            row = repository.resume_select_assignments(db, (run_id,)).fetchone()
            if (
                body["status"] != "PAUSED"
                or not row
                or not row["released"]
                or json.loads(row["snapshot"])["state"]["status"] != "PAUSED"
            ):
                raise ServiceError(409, "Wait for the completed checkpoint and confirmed resource release")
            if reason := store.eligibility(db, body):
                raise ServiceError(409, reason)
            body.update(status="QUEUED", resumeRequested=True, pauseRequested=False, cancelRequested=False)
            body.pop("waitingReason", None)
            store.save(db, body)
            repository.resume_insert_queue(db, (run_id,))
            store.audit(db, current["userId"], "RESUME_REQUESTED", run_id, body["workspaceId"])
        return body

    def backup_policy(run_id: str, policy: BackupPolicy, *, current):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] in TERMINAL:
                raise ServiceError(409, "Experiment is already finished")
            assignment = repository.backup_policy_select_assignments(db, (run_id,)).fetchone()
            if assignment and not assignment["released"]:
                runtime.require_command(db, assignment["coordinator"], "UPDATE_BACKUP_POLICY")
                runtime.enqueue(
                    db,
                    assignment["coordinator"],
                    "UPDATE_BACKUP_POLICY",
                    {"assignmentId": assignment["id"], "epoch": assignment["epoch"], "policy": policy.model_dump()},
                    "backup-policy:" + secrets.token_hex(16),
                )
            body["requestedBackupPolicy"] = policy.model_dump()
            store.save(db, body)
            store.audit(db, current["userId"], "BACKUP_POLICY_REQUESTED", run_id, body["workspaceId"])
        return {"policy": policy.model_dump(), "appliesBeforeNextGeneration": True}

    def members(run_id: str, request: MembershipRequest, *, current):
        """Add or remove a worker while the experiment runs (ADR-009); it applies at the next generation boundary."""
        action = {"add": "JOIN", "remove": "LEAVE", "retry": "RETRY"}[request.action]
        with store.db() as db:
            begin_write(db)
            authorized(run_id, current)
            try:
                change = runtime.change_members(db, run_id, request.workerId, action, current["username"])
            except RuntimeRejected as error:
                raise ServiceError(409, str(error)) from None
            runtime.note_membership(db, run_id, change, current["userId"])
        return {**change, "appliesAtNextGeneration": action != "RETRY"}

    def queue(*, current):
        with store.db() as db:
            held = dispatch_held(db)
            positions = {r["run_id"]: i + 1 for i, r in enumerate(repository.queue_select_queue(db))}
            result = []
            for r in repository.queue_select_experiments(db):
                b = json.loads(r[0])
                if (
                    b["workspaceId"] == current["workspaceId"]
                    and b["experimentId"] in positions
                    and (current["workspaceRole"] == "ADMIN" or b["ownerUserId"] == current["userId"])
                ):
                    result.append(
                        {
                            "experimentId": b["experimentId"],
                            "position": positions[b["experimentId"]],
                            "reason": "Maintenance hold"
                            if held
                            else b.get("waitingReason", "Waiting for runtime release")
                            if b["status"] == "QUEUED"
                            else b["status"],
                        }
                    )
            return result

    return SimpleNamespace(
        experiments=experiments,
        create=create,
        experiment=experiment,
        run_timeline=run_timeline,
        edit=edit,
        submit=submit,
        cancel=cancel,
        archive=archive,
        pause=pause,
        resume=resume,
        backup_policy=backup_policy,
        members=members,
        queue=queue,
    )
