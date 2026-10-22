"""Identity and membership operations, independent of runtime numerical state."""

from .request_models import DefaultCoordinator, WorkspaceCreate, Invite, JoinDecision, Listing, MemberEdit
from .policies import dispatch_held, set_disabled_workers
import json
import sqlite3
import uuid

from fastapi import Depends, HTTPException, Response

from .store import now


from fastapi import APIRouter


def install_routes(app, store, scoped, active, workspace_admin):
    router = APIRouter()

    @router.post("/api/v1/workspaces", status_code=201)
    def create_workspace(body: WorkspaceCreate, current=Depends(active)):
        with store.db() as db:
            current = active(current)
            if not current.get("canCreateWorkspace"):
                raise HTTPException(403, "Workspace creation permission required")
            wid = uuid.uuid4().hex
            db.execute("INSERT INTO workspaces VALUES (?,?,?,?)", (wid, body.name, body.description, current["userId"]))
            db.execute("INSERT INTO memberships VALUES (?,?,?)", (wid, current["userId"], "ADMIN"))
            store.audit(db, current["userId"], "WORKSPACE_CREATE", wid, wid)
            return {
                "workspaceId": wid,
                "name": body.name,
                "description": body.description,
                "creatorUserId": current["userId"],
                "role": "ADMIN",
            }

    @router.post("/api/v1/workspaces/{workspace_id}/invitations", status_code=201)
    def invite(workspace_id: str, body: Invite, current=Depends(active)):
        with store.db() as db:
            workspace_admin(workspace_id, current)
            target = db.execute(
                "SELECT id,profile FROM users WHERE json_extract(profile,'$.username')=?", (body.username,)
            ).fetchone()
            if not target or json.loads(target["profile"])["accountStatus"] != "ACTIVE":
                raise HTTPException(422, "Invite an approved account by username")
            if db.execute(
                "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", (workspace_id, target["id"])
            ).fetchone():
                raise HTTPException(409, "Account is already a member")
            iid = uuid.uuid4().hex
            try:
                db.execute(
                    "INSERT INTO invitations VALUES (?,?,?,?,?)", (iid, workspace_id, target["id"], "PENDING", now())
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "A pending invitation already exists") from None
            store.audit(db, current["userId"], "INVITE", target["id"], workspace_id)
            return {"invitationId": iid, "workspaceId": workspace_id, "username": body.username, "status": "PENDING"}

    def coordinator_devices(db, workspace_id):
        return {
            r["id"]
            for r in db.execute(
                'SELECT d.id,d.self_test FROM devices d JOIN worker_assignments a ON a.worker_id=d.worker_id WHERE d.status="APPROVED" AND a.workspace_id=?',
                (workspace_id,),
            )
            if json.loads(r["self_test"]).get("coordinator")
        }

    def settings(db, workspace_id):
        row = db.execute("SELECT body FROM workspace_settings WHERE workspace_id=?", (workspace_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_settings(db, workspace_id, changes):
        body = {**settings(db, workspace_id), **changes}
        db.execute("INSERT OR REPLACE INTO workspace_settings VALUES (?,?)", (workspace_id, json.dumps(body)))
        return body

    @router.patch("/api/v1/workspaces/{workspace_id}/listing")
    def listing(workspace_id: str, body: Listing, current=Depends(active)):
        # a listed workspace appears in every active user's list and accepts join requests
        workspace_admin(workspace_id, current)
        with store.db() as db:
            save_settings(db, workspace_id, {"listed": body.listed})
            store.audit(
                db,
                current["userId"],
                "WORKSPACE_LISTED" if body.listed else "WORKSPACE_UNLISTED",
                workspace_id,
                workspace_id,
            )
        return {"workspaceId": workspace_id, "listed": body.listed}

    @router.patch("/api/v1/workspaces/{workspace_id}/default-coordinator")
    def default_coordinator(workspace_id: str, body: DefaultCoordinator, current=Depends(active)):
        # pre-filled in the experiment form; the creator can still choose another coordinator
        workspace_admin(workspace_id, current)
        with store.db() as db:
            if body.deviceId is not None and body.deviceId not in coordinator_devices(db, workspace_id):
                raise HTTPException(422, "Select an approved coordinator in this workspace")
            save_settings(db, workspace_id, {"defaultCoordinatorDeviceId": body.deviceId})
            store.audit(db, current["userId"], "DEFAULT_COORDINATOR", body.deviceId or "", workspace_id)
        return {"workspaceId": workspace_id, "defaultCoordinatorDeviceId": body.deviceId}

    @router.get("/api/v1/listed-workspaces")
    def listed_workspaces(current=Depends(active)):
        with store.db() as db:
            rows = db.execute("SELECT w.* FROM workspaces w ORDER BY w.rowid").fetchall()
            member = {
                r[0] for r in db.execute("SELECT workspace_id FROM memberships WHERE user_id=?", (current["userId"],))
            }
            requested = {
                r[0]
                for r in db.execute(
                    'SELECT workspace_id FROM join_requests WHERE user_id=? AND status="PENDING"', (current["userId"],)
                )
            }
            return [
                {
                    "workspaceId": r["id"],
                    "name": r["name"],
                    "description": r["description"],
                    "member": r["id"] in member,
                    "requested": r["id"] in requested,
                }
                for r in rows
                if settings(db, r["id"]).get("listed")
            ]

    @router.post("/api/v1/workspaces/{workspace_id}/join-requests", status_code=201)
    def ask_to_join(workspace_id: str, current=Depends(active)):
        with store.db() as db:
            if not db.execute("SELECT 1 FROM workspaces WHERE id=?", (workspace_id,)).fetchone() or not settings(
                db, workspace_id
            ).get("listed"):
                raise HTTPException(404, "Workspace not found")
            if db.execute(
                "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", (workspace_id, current["userId"])
            ).fetchone():
                raise HTTPException(409, "Already a member")
            rid = uuid.uuid4().hex
            try:
                db.execute(
                    "INSERT INTO join_requests VALUES (?,?,?,?,?)",
                    (rid, workspace_id, current["userId"], "PENDING", now()),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "A request is already waiting") from None
            store.audit(db, current["userId"], "JOIN_REQUEST", rid, workspace_id)
            return {"requestId": rid, "workspaceId": workspace_id, "status": "PENDING"}

    @router.get("/api/v1/workspaces/{workspace_id}/join-requests")
    def join_requests(workspace_id: str, current=Depends(active)):
        workspace_admin(workspace_id, current)
        with store.db() as db:
            return [
                {
                    "requestId": r["id"],
                    "userId": r["user_id"],
                    "username": json.loads(r["profile"])["username"],
                    "displayName": json.loads(r["profile"]).get("displayName"),
                    "createdAt": r["created"],
                }
                for r in db.execute(
                    'SELECT j.*,u.profile FROM join_requests j JOIN users u ON u.id=j.user_id WHERE j.workspace_id=? AND j.status="PENDING" ORDER BY j.rowid',
                    (workspace_id,),
                )
            ]

    @router.post("/api/v1/workspaces/{workspace_id}/join-requests/{request_id}")
    def decide_join(workspace_id: str, request_id: str, body: JoinDecision, current=Depends(active)):
        workspace_admin(workspace_id, current)
        with store.db() as db:
            row = db.execute(
                "SELECT * FROM join_requests WHERE id=? AND workspace_id=?", (request_id, workspace_id)
            ).fetchone()
            if not row or row["status"] != "PENDING":
                raise HTTPException(404, "Pending request not found")
            status = "APPROVED" if body.approve else "REJECTED"
            if body.approve:
                db.execute(
                    "INSERT OR IGNORE INTO memberships VALUES (?,?,?)", (workspace_id, row["user_id"], "PARTICIPANT")
                )
            db.execute("UPDATE join_requests SET status=? WHERE id=?", (status, request_id))
            store.audit(db, current["userId"], "JOIN_" + status, row["user_id"], workspace_id)
            return {"requestId": request_id, "status": status}

    @router.get("/api/v1/my-invitations")
    def invitations(current=Depends(active)):
        with store.db() as db:
            return [
                {
                    "invitationId": r["id"],
                    "workspaceId": r["workspace_id"],
                    "workspaceName": r["name"],
                    "username": current["username"],
                    "email": "",
                    "status": r["status"],
                    "createdAt": r["created"],
                }
                for r in db.execute(
                    'SELECT i.*,w.name FROM invitations i JOIN workspaces w ON w.id=i.workspace_id WHERE i.user_id=? AND i.status="PENDING"',
                    (current["userId"],),
                )
            ]

    @router.post("/api/v1/my-invitations/{invitation_id}/accept")
    def accept(invitation_id: str, current=Depends(active)):
        with store.db() as db:
            active(current)
            row = db.execute(
                "SELECT * FROM invitations WHERE id=? AND user_id=?", (invitation_id, current["userId"])
            ).fetchone()
            if not row or row["status"] != "PENDING":
                raise HTTPException(404, "Pending invitation not found")
            db.execute(
                "INSERT OR IGNORE INTO memberships VALUES (?,?,?)",
                (row["workspace_id"], current["userId"], "PARTICIPANT"),
            )
            db.execute('UPDATE invitations SET status="ACCEPTED" WHERE id=?', (invitation_id,))
            store.audit(db, current["userId"], "INVITATION_ACCEPT", invitation_id, row["workspace_id"])
            return {"invitationId": invitation_id, "workspaceId": row["workspace_id"], "status": "ACCEPTED"}

    def member_change(db, workspace_id, user_id, current, role=None):
        workspace_admin(workspace_id, current)
        old = db.execute(
            "SELECT role FROM memberships WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)
        ).fetchone()
        if not old:
            raise HTTPException(404, "Member not found")
        if old[0] == "ADMIN" and role != "ADMIN":
            others = db.execute(
                "SELECT count(*) FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND m.role='ADMIN' AND m.user_id<>? AND json_extract(u.profile,'$.accountStatus')='ACTIVE'",
                (workspace_id, user_id),
            ).fetchone()[0]
            if others == 0:
                raise HTTPException(409, "Keep at least one workspace administrator")
        if user_id == current["userId"] and (role is None or (old[0] == "ADMIN" and role != "ADMIN")):
            raise HTTPException(409, "You cannot remove your own membership or administrator role")
        if role:
            db.execute(
                "UPDATE memberships SET role=? WHERE workspace_id=? AND user_id=?", (role, workspace_id, user_id)
            )
        else:
            db.execute("DELETE FROM memberships WHERE workspace_id=? AND user_id=?", (workspace_id, user_id))
            db.execute(
                'UPDATE invitations SET status="REVOKED" WHERE workspace_id=? AND user_id=? AND status="PENDING"',
                (workspace_id, user_id),
            )
            store.cancel_owned(db, user_id, workspace_id)
            disabled = store.disabled_workers(db)
            for r in db.execute(
                "SELECT worker_id FROM worker_assignments WHERE owner=? AND workspace_id=?", (user_id, workspace_id)
            ).fetchall():
                disabled.add(r[0])
                store.cancel_selected(db, r[0])
            set_disabled_workers(db, disabled)
        store.audit(db, current["userId"], "MEMBER_ROLE" if role else "MEMBER_REMOVE", user_id, workspace_id)

    @router.patch("/api/v1/workspaces/{workspace_id}/members/{user_id}")
    def change_role(workspace_id: str, user_id: str, body: MemberEdit, current=Depends(active)):
        with store.db() as db:
            member_change(db, workspace_id, user_id, current, body.role)
        return {"userId": user_id, "role": body.role}

    @router.delete("/api/v1/workspaces/{workspace_id}/members/{user_id}", status_code=204)
    def remove_member(workspace_id: str, user_id: str, current=Depends(active)):
        with store.db() as db:
            member_change(db, workspace_id, user_id, current)
        return Response(status_code=204)

    @router.get("/api/v1/queue")
    def queue(current=Depends(scoped)):
        with store.db() as db:
            held = dispatch_held(db)
            positions = {
                r["run_id"]: i + 1 for i, r in enumerate(db.execute("SELECT run_id FROM queue ORDER BY sequence"))
            }
            result = []
            for r in db.execute("SELECT body FROM experiments"):
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

    app.include_router(router)
