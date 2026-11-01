"""Workspace membership, admission and queue visibility business operations."""

import json
import uuid
from types import SimpleNamespace
from ..request_models import DefaultCoordinator, WorkspaceCreate, Invite, JoinDecision, Listing, MemberEdit
from ..policies import dispatch_held, set_disabled_workers
from ..store import now
from ..core.errors import ServiceError, DatabaseConflict
from ..repositories.workspaces import WorkspacesRepository as repository


def operations(store, scoped, active, workspace_admin):
    def create_workspace(body: WorkspaceCreate, *, current):
        with store.db() as db:
            current = active(current)
            if not current.get("canCreateWorkspace"):
                raise ServiceError(403, "Workspace creation permission required")
            wid = uuid.uuid4().hex
            repository.create_workspace_insert_workspaces(db, (wid, body.name, body.description, current["userId"]))
            repository.create_workspace_insert_memberships(db, (wid, current["userId"], "ADMIN"))
            store.audit(db, current["userId"], "WORKSPACE_CREATE", wid, wid)
            return {
                "workspaceId": wid,
                "name": body.name,
                "description": body.description,
                "creatorUserId": current["userId"],
                "role": "ADMIN",
            }

    def invite(workspace_id: str, body: Invite, *, current):
        with store.db() as db:
            workspace_admin(workspace_id, current)
            target = repository.invite_select_users(db, (body.username,)).fetchone()
            if not target or json.loads(target["profile"])["accountStatus"] != "ACTIVE":
                raise ServiceError(422, "Invite an approved account by username")
            if repository.invite_select_memberships(db, (workspace_id, target["id"])).fetchone():
                raise ServiceError(409, "Account is already a member")
            iid = uuid.uuid4().hex
            try:
                repository.invite_insert_invitations(db, (iid, workspace_id, target["id"], "PENDING", now()))
            except DatabaseConflict:
                raise ServiceError(409, "A pending invitation already exists") from None
            store.audit(db, current["userId"], "INVITE", target["id"], workspace_id)
            return {"invitationId": iid, "workspaceId": workspace_id, "username": body.username, "status": "PENDING"}

    def coordinator_devices(db, workspace_id):
        return {
            r["id"]
            for r in repository.coordinator_devices_select_devices(db, (workspace_id,))
            if json.loads(r["self_test"]).get("coordinator")
        }

    def settings(db, workspace_id):
        row = repository.settings_select_workspace_settings(db, (workspace_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_settings(db, workspace_id, changes):
        body = {**settings(db, workspace_id), **changes}
        repository.save_settings_insert_workspace_settings(db, (workspace_id, json.dumps(body)))
        return body

    def listing(workspace_id: str, body: Listing, *, current):
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

    def default_coordinator(workspace_id: str, body: DefaultCoordinator, *, current):
        # pre-filled in the experiment form; the creator can still choose another coordinator
        workspace_admin(workspace_id, current)
        with store.db() as db:
            if body.deviceId is not None and body.deviceId not in coordinator_devices(db, workspace_id):
                raise ServiceError(422, "Select an approved coordinator in this workspace")
            save_settings(db, workspace_id, {"defaultCoordinatorDeviceId": body.deviceId})
            store.audit(db, current["userId"], "DEFAULT_COORDINATOR", body.deviceId or "", workspace_id)
        return {"workspaceId": workspace_id, "defaultCoordinatorDeviceId": body.deviceId}

    def listed_workspaces(*, current):
        with store.db() as db:
            rows = repository.listed_workspaces_select_workspaces(db).fetchall()
            member = {r[0] for r in repository.listed_workspaces_select_memberships(db, (current["userId"],))}
            requested = {r[0] for r in repository.listed_workspaces_select_join_requests(db, (current["userId"],))}
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

    def ask_to_join(workspace_id: str, *, current):
        with store.db() as db:
            if not repository.ask_to_join_select_workspaces(db, (workspace_id,)).fetchone() or not settings(
                db, workspace_id
            ).get("listed"):
                raise ServiceError(404, "Workspace not found")
            if repository.ask_to_join_select_memberships(db, (workspace_id, current["userId"])).fetchone():
                raise ServiceError(409, "Already a member")
            rid = uuid.uuid4().hex
            try:
                repository.ask_to_join_insert_join_requests(
                    db, (rid, workspace_id, current["userId"], "PENDING", now())
                )
            except DatabaseConflict:
                raise ServiceError(409, "A request is already waiting") from None
            store.audit(db, current["userId"], "JOIN_REQUEST", rid, workspace_id)
            return {"requestId": rid, "workspaceId": workspace_id, "status": "PENDING"}

    def join_requests(workspace_id: str, *, current):
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
                for r in repository.join_requests_select_join_requests(db, (workspace_id,))
            ]

    def decide_join(workspace_id: str, request_id: str, body: JoinDecision, *, current):
        workspace_admin(workspace_id, current)
        with store.db() as db:
            row = repository.decide_join_select_join_requests(db, (request_id, workspace_id)).fetchone()
            if not row or row["status"] != "PENDING":
                raise ServiceError(404, "Pending request not found")
            status = "APPROVED" if body.approve else "REJECTED"
            if body.approve:
                repository.decide_join_insert_memberships(db, (workspace_id, row["user_id"], "PARTICIPANT"))
            repository.decide_join_update_join_requests(db, (status, request_id))
            store.audit(db, current["userId"], "JOIN_" + status, row["user_id"], workspace_id)
            return {"requestId": request_id, "status": status}

    def invitations(*, current):
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
                for r in repository.invitations_select_invitations(db, (current["userId"],))
            ]

    def accept(invitation_id: str, *, current):
        with store.db() as db:
            active(current)
            row = repository.accept_select_invitations(db, (invitation_id, current["userId"])).fetchone()
            if not row or row["status"] != "PENDING":
                raise ServiceError(404, "Pending invitation not found")
            repository.accept_insert_memberships(db, (row["workspace_id"], current["userId"], "PARTICIPANT"))
            repository.accept_update_invitations(db, (invitation_id,))
            store.audit(db, current["userId"], "INVITATION_ACCEPT", invitation_id, row["workspace_id"])
            return {"invitationId": invitation_id, "workspaceId": row["workspace_id"], "status": "ACCEPTED"}

    def member_change(db, workspace_id, user_id, current, role=None):
        workspace_admin(workspace_id, current)
        old = repository.member_change_select_memberships(db, (workspace_id, user_id)).fetchone()
        if not old:
            raise ServiceError(404, "Member not found")
        if old[0] == "ADMIN" and role != "ADMIN":
            others = repository.member_change_select_memberships_2(db, (workspace_id, user_id)).fetchone()[0]
            if others == 0:
                raise ServiceError(409, "Keep at least one workspace administrator")
        if user_id == current["userId"] and (role is None or (old[0] == "ADMIN" and role != "ADMIN")):
            raise ServiceError(409, "You cannot remove your own membership or administrator role")
        if role:
            repository.member_change_update_memberships(db, (role, workspace_id, user_id))
        else:
            repository.member_change_delete_memberships(db, (workspace_id, user_id))
            repository.member_change_update_invitations(db, (workspace_id, user_id))
            store.cancel_owned(db, user_id, workspace_id)
            disabled = store.disabled_workers(db)
            for r in repository.member_change_select_worker_assignments(db, (user_id, workspace_id)).fetchall():
                disabled.add(r[0])
                store.cancel_selected(db, r[0])
            set_disabled_workers(db, disabled)
        store.audit(db, current["userId"], "MEMBER_ROLE" if role else "MEMBER_REMOVE", user_id, workspace_id)

    def change_role(workspace_id: str, user_id: str, body: MemberEdit, *, current):
        with store.db() as db:
            member_change(db, workspace_id, user_id, current, body.role)
        return {"userId": user_id, "role": body.role}

    def remove_member(workspace_id: str, user_id: str, *, current):
        with store.db() as db:
            member_change(db, workspace_id, user_id, current)
        return None

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
        create_workspace=create_workspace,
        invite=invite,
        listing=listing,
        default_coordinator=default_coordinator,
        listed_workspaces=listed_workspaces,
        ask_to_join=ask_to_join,
        join_requests=join_requests,
        decide_join=decide_join,
        invitations=invitations,
        accept=accept,
        change_role=change_role,
        remove_member=remove_member,
        queue=queue,
    )
