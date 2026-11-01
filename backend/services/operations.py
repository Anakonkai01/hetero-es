"""Operations business operations; HTTP responses stay in api/."""

from ..core.request_models import AccountEdit, Resume
from .policies import dispatch_held, set_disabled_workers, storage_status
import json
from ..core.constants import ACTIVE
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.operations import OperationsRepository as repository


def operations(store, runtime, platform):
    def users(*, current):
        with store.db() as db:
            return [json.loads(r[0]) for r in repository.users_select_users(db, ())]

    def edit_account(user_id: str, body: AccountEdit, *, current):
        with store.db() as db:
            platform(current)
            old = store.profile(user_id)
            if not old:
                raise ServiceError(404, "Account not found")
            updated = {**old, **body.model_dump(exclude_none=True)}
            if old.get("platformAdmin") and (not updated["platformAdmin"] or updated["accountStatus"] != "ACTIVE"):
                others = [json.loads(r[0]) for r in repository.edit_account_select_users(db, (user_id,))]
                if not any(p.get("platformAdmin") and p["accountStatus"] == "ACTIVE" for p in others):
                    raise ServiceError(409, "Keep at least one active platform administrator")
            if user_id == current["userId"] and (
                updated.get("accountStatus") != "ACTIVE"
                or (old.get("platformAdmin") and not updated.get("platformAdmin"))
                or (old.get("canCreateWorkspace") and not updated.get("canCreateWorkspace"))
            ):
                raise ServiceError(409, "You cannot remove your own access or permissions")
            repository.edit_account_update_users(db, (json.dumps(updated), user_id))
            if updated["accountStatus"] != "ACTIVE":
                repository.edit_account_delete_sessions(db, (user_id,))
                store.cancel_owned(db, user_id)
                disabled = store.disabled_workers(db)
                for r in repository.edit_account_select_worker_assignments(db, (user_id,)).fetchall():
                    disabled.add(r[0])
                    store.cancel_selected(db, r[0])
                set_disabled_workers(db, disabled)
            store.audit(db, current["userId"], "ACCOUNT_UPDATE", user_id)
            return updated

    def revoke_sessions(user_id: str, *, current):
        with store.db() as db:
            platform(current)
            if not store.profile(user_id):
                raise ServiceError(404, "Account not found")
            if user_id == current["userId"]:
                raise ServiceError(409, "Use your account security page to sign out other sessions")
            repository.revoke_sessions_delete_sessions(db, (user_id,))
            store.audit(db, current["userId"], "REVOKE_SESSIONS", user_id)
        return None

    def platform_audit(*, current):
        with store.db() as db:
            return [dict(r) for r in repository.platform_audit_select_audit(db, ())]

    def operations(*, current):
        with store.db() as db:
            held = dispatch_held(db)
            queue_count = repository.operations_select_queue(db, ()).fetchone()[0]
            metadata = repository.operations_select_settings(db, ()).fetchone()
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

    def resume(body: Resume, *, current):
        with store.operation_lock:
            platform(current)
            cap = runtime.capabilities()
            with store.db() as db:
                selected = {wid for b in store.list() if b["status"] == "QUEUED" for wid in b["workerIds"]}
                if not selected <= set(cap["workerIds"]):
                    raise ServiceError(
                        409,
                        "Configure all imported queued worker IDs or cancel their queued experiments before resuming",
                    )
                repository.resume_update_settings(db, ())
                # Holds left by the removed M1 maintenance (begin_maintenance) are cleared too.
                repository.resume_delete_settings(db, ())
                store.audit(db, current["userId"], "MAINTENANCE_END", "deployment")
        return {"dispatchHeld": False}

    return SimpleNamespace(
        users=users,
        edit_account=edit_account,
        revoke_sessions=revoke_sessions,
        platform_audit=platform_audit,
        operations=operations,
        resume=resume,
    )
