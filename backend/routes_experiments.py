from .errors import RuntimeRejected
from .request_models import BackupPolicy, Configuration, MembershipRequest
from .policies import dispatch_held
import hashlib
import json
import secrets

from fastapi import Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from .store import TERMINAL, now
from .constants import REVISION
from .timeline import build_timeline


from fastapi import APIRouter


def install_routes(app, store, runtime, scoped, visible, authorized, validate):
    router = APIRouter()

    @router.get("/api/v1/experiments")
    def experiments(current=Depends(scoped)):
        return visible(current)

    @router.post("/api/v1/experiments")
    def create(body: Configuration, current=Depends(scoped)):
        with store.lock:
            return store.create(current["userId"], validate(body, current), current["workspaceId"])

    @router.get("/api/v1/experiments/{run_id}")
    def experiment(run_id: str, current=Depends(scoped)):
        return authorized(run_id, current)

    @router.get("/api/v1/experiments/{run_id}/timeline")
    def run_timeline(run_id: str, current=Depends(scoped)):
        return build_timeline(authorized(run_id, current), store.snapshot(run_id))

    @router.get("/api/v1/experiments/{run_id}/stream")
    def run_stream(run_id: str, current=Depends(scoped)):
        authorized(run_id, current)
        if not app.state.live.acquire():
            raise HTTPException(429, "Too many live views are open. Close one and try again.")
        return StreamingResponse(
            app.state.live.frames(store, run_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @router.patch("/api/v1/experiments/{run_id}")
    def edit(run_id: str, request: dict, current=Depends(scoped)):
        with store.db() as db:
            old = authorized(run_id, current)
            if old["status"] != "DRAFT":
                raise HTTPException(409, "Submitted configuration is immutable")
            try:
                body = validate(Configuration(**request), current)
            except ValueError:
                raise HTTPException(422, "Invalid configuration") from None
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

    @router.post("/api/v1/experiments/{run_id}/submit")
    def submit(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] == "DRAFT":
                if dispatch_held(db):
                    raise HTTPException(409, "Submissions are held for maintenance or restored deployment review")
                if reason := store.eligibility(db, body):
                    raise HTTPException(409, reason)
                body["status"] = "QUEUED"
                db.execute("INSERT INTO queue(run_id) VALUES (?)", (run_id,))
                store.save(db, body)
                store.audit(db, current["userId"], "SUBMIT", run_id, current["workspaceId"])
            elif body["status"] in TERMINAL:
                raise HTTPException(409, "Experiment already finished")
            return body

    @router.post("/api/v1/experiments/{run_id}/cancel")
    def cancel(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] in TERMINAL:
                return body
            body["cancelRequested"] = True
            if body["status"] in ("DRAFT", "QUEUED", "PAUSED"):
                body.update(status="CANCELLED", completedAt=now())
                db.execute("DELETE FROM queue WHERE run_id=?", (run_id,))
            else:
                body["status"] = "CANCELLING"
            store.save(db, body)
            store.audit(db, current["userId"], "CANCEL", run_id, current["workspaceId"])
            return body

    @router.delete("/api/v1/experiments/{run_id}", status_code=204)
    def archive(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] not in TERMINAL | {"DRAFT"}:
                raise HTTPException(409, "Cancel and wait for the experiment to finish before archiving")
            body["archivedAt"] = now()
            store.save(db, body)
            store.audit(db, current["userId"], "ARCHIVE", run_id, current["workspaceId"])
        return Response(status_code=204)

    @router.post("/api/v1/experiments/{run_id}/pause")
    def pause(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            body = authorized(run_id, current)
            if body["status"] == "PAUSED":
                return body
            if body.get("cancelRequested") or body["status"] not in ("STARTING", "RUNNING", "PAUSING"):
                raise HTTPException(409, "Pause requires a running experiment")
            runtime.require_command(db, body["coordinatorDeviceId"], "PAUSE_ASSIGNMENT")
            runtime.pause(run_id, db=db)
            body.update(pauseRequested=True, status="PAUSING")
            store.save(db, body)
            store.audit(db, current["userId"], "PAUSE_REQUESTED", run_id, body["workspaceId"])
        return body

    @router.post("/api/v1/experiments/{run_id}/resume")
    def resume(run_id: str, current=Depends(scoped)):
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            body = authorized(run_id, current)
            if body.get("resumeRequested") and body["status"] in ("QUEUED", "STARTING"):
                return body
            row = db.execute(
                "SELECT released,snapshot FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (run_id,)
            ).fetchone()
            if (
                body["status"] != "PAUSED"
                or not row
                or not row["released"]
                or json.loads(row["snapshot"])["state"]["status"] != "PAUSED"
            ):
                raise HTTPException(409, "Wait for the completed checkpoint and confirmed resource release")
            if reason := store.eligibility(db, body):
                raise HTTPException(409, reason)
            body.update(status="QUEUED", resumeRequested=True, pauseRequested=False, cancelRequested=False)
            body.pop("waitingReason", None)
            store.save(db, body)
            db.execute("INSERT OR IGNORE INTO queue(run_id) VALUES (?)", (run_id,))
            store.audit(db, current["userId"], "RESUME_REQUESTED", run_id, body["workspaceId"])
        return body

    @router.patch("/api/v1/experiments/{run_id}/backup-policy")
    def backup_policy(run_id: str, policy: BackupPolicy, current=Depends(scoped)):
        with store.db() as db:
            body = authorized(run_id, current)
            if body["status"] in TERMINAL:
                raise HTTPException(409, "Experiment is already finished")
            assignment = db.execute(
                "SELECT id,coordinator,epoch,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1",
                (run_id,),
            ).fetchone()
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

    @router.post("/api/v1/experiments/{run_id}/workers")
    def members(run_id: str, request: MembershipRequest, current=Depends(scoped)):
        """Add or remove a worker while the experiment runs (ADR-009); it applies at the next generation boundary."""
        action = "JOIN" if request.action == "add" else "LEAVE"
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            authorized(run_id, current)
            try:
                change = runtime.change_members(db, run_id, request.workerId, action, current["username"])
            except RuntimeRejected as error:
                raise HTTPException(409, str(error)) from None
            runtime.note_membership(db, run_id, change, current["userId"])
        return {**change, "appliesAtNextGeneration": True}

    app.include_router(router)
