"""Identity and membership operations, independent of runtime numerical state."""

from .request_models import AccountEdit, Resume
from .policies import dispatch_held, set_disabled_workers, storage_status
import json

from fastapi import Depends, HTTPException, Response

from .store import ACTIVE


from fastapi import APIRouter


def install_routes(app, store, runtime, platform):
    router = APIRouter()

    @router.get("/api/v1/platform/users")
    def users(current=Depends(platform)):
        with store.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT profile FROM users ORDER BY rowid")]

    @router.patch("/api/v1/platform/users/{user_id}")
    def edit_account(user_id: str, body: AccountEdit, current=Depends(platform)):
        with store.db() as db:
            platform(current)
            old = store.profile(user_id)
            if not old:
                raise HTTPException(404, "Account not found")
            updated = {**old, **body.model_dump(exclude_none=True)}
            if old.get("platformAdmin") and (not updated["platformAdmin"] or updated["accountStatus"] != "ACTIVE"):
                others = [json.loads(r[0]) for r in db.execute("SELECT profile FROM users WHERE id<>?", (user_id,))]
                if not any(p.get("platformAdmin") and p["accountStatus"] == "ACTIVE" for p in others):
                    raise HTTPException(409, "Keep at least one active platform administrator")
            db.execute("UPDATE users SET profile=? WHERE id=?", (json.dumps(updated), user_id))
            if updated["accountStatus"] != "ACTIVE":
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                store.cancel_owned(db, user_id)
                disabled = store.disabled_workers(db)
                for r in db.execute("SELECT worker_id FROM worker_assignments WHERE owner=?", (user_id,)).fetchall():
                    disabled.add(r[0])
                    store.cancel_selected(db, r[0])
                set_disabled_workers(db, disabled)
            store.audit(db, current["userId"], "ACCOUNT_UPDATE", user_id)
            return updated

    @router.post("/api/v1/platform/users/{user_id}/revoke-sessions", status_code=204)
    def revoke_sessions(user_id: str, current=Depends(platform)):
        with store.db() as db:
            platform(current)
            if not store.profile(user_id):
                raise HTTPException(404, "Account not found")
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            store.audit(db, current["userId"], "REVOKE_SESSIONS", user_id)
        return Response(status_code=204)

    @router.get("/api/v1/platform/audit")
    def platform_audit(current=Depends(platform)):
        with store.db() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM audit WHERE workspace_id IS NULL ORDER BY sequence DESC LIMIT 200")
            ]

    @router.get("/api/v1/platform/operations")
    def operations(current=Depends(platform)):
        with store.db() as db:
            held = dispatch_held(db)
            queue_count = db.execute("SELECT count(*) FROM queue").fetchone()[0]
            metadata = db.execute('SELECT value FROM settings WHERE key="metadataBackupStatus"').fetchone()
        result = {
            "dispatchHeld": held,
            "queueCount": queue_count,
            "runtimeIssue": store.last_error,
            **storage_status(runtime),
            "metadataBackup": json.loads(metadata[0]) if metadata else None,
            "productService": "ONLINE",
            "runtimeService": "UNAVAILABLE",
            "workers": [],
            "reservations": [],
        }
        try:
            cap = runtime.capabilities()
            store.ensure_workers(cap["workerIds"])
            runs = runtime.runs()
            result.update(
                runtimeService="ONLINE",
                workers=runtime.workers(),
                quarantinedWorkerIds=cap.get("quarantinedWorkerIds", []),
                reservations=[
                    {
                        "runId": r["runId"],
                        "status": r["status"],
                        "workerStates": r.get("workerStates", {}),
                        "failureReason": r.get("failureReason"),
                    }
                    for r in runs
                    if r["status"] in ACTIVE
                ],
                recentFailures=[
                    {"runId": r["runId"], "status": r["status"], "failureReason": r.get("failureReason")}
                    for r in sorted(runs, key=lambda r: r.get("startedAt", 0), reverse=True)
                    if r.get("failureReason")
                ][:20],
            )
        except Exception as error:
            result["runtimeIssue"] = type(error).__name__
        return result

    @router.post("/api/v1/platform/maintenance/resume")
    def resume(body: Resume, current=Depends(platform)):
        with store.operation_lock:
            platform(current)
            cap = runtime.capabilities()
            with store.db() as db:
                selected = {wid for b in store.list() if b["status"] == "QUEUED" for wid in b["workerIds"]}
                if not selected <= set(cap["workerIds"]):
                    raise HTTPException(
                        409,
                        "Configure all imported queued worker IDs or cancel their queued experiments before resuming",
                    )
                db.execute('UPDATE settings SET value="false" WHERE key="dispatchHold"')
                # Holds left by the removed M1 maintenance (begin_maintenance) are cleared too.
                db.execute('DELETE FROM settings WHERE key IN ("maintenanceId","agentMaintenance")')
                store.audit(db, current["userId"], "MAINTENANCE_END", "deployment")
        return {"dispatchHeld": False}

    app.include_router(router)
