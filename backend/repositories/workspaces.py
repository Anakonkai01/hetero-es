"""Workspace SQL; transaction boundaries belong to business operations."""

from ..db.dialect import json_text
from .base import execute


class WorkspacesRepository:
    @staticmethod
    def create_workspace_insert_workspaces(db, parameters=()):
        return execute(db, "INSERT INTO workspaces(id,name,description,creator)  VALUES (:p0,:p1,:p2,:p3)", parameters)

    @staticmethod
    def create_workspace_insert_memberships(db, parameters=()):
        return execute(db, "INSERT INTO memberships(workspace_id,user_id,role)  VALUES (:p0,:p1,:p2)", parameters)

    @staticmethod
    def invite_insert_invitations(db, parameters=()):
        return execute(
            db,
            "INSERT INTO invitations(id,workspace_id,user_id,status,created)  VALUES (:p0,:p1,:p2,:p3,:p4)",
            parameters,
        )

    @staticmethod
    def invite_select_users(db, parameters=()):
        return execute(db, f"SELECT id,profile FROM users WHERE {json_text(db, 'profile', 'username')}=:p0", parameters)

    @staticmethod
    def invite_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def coordinator_devices_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT d.id,d.self_test FROM devices d JOIN worker_assignments a ON a.worker_id=d.worker_id WHERE d.status='APPROVED' AND a.workspace_id=:p0",
            parameters,
        )

    @staticmethod
    def settings_select_workspace_settings(db, parameters=()):
        return execute(db, "SELECT body FROM workspace_settings WHERE workspace_id=:p0", parameters)

    @staticmethod
    def save_settings_insert_workspace_settings(db, parameters=()):
        return execute(
            db,
            "INSERT INTO workspace_settings(workspace_id,body)  VALUES (:p0,:p1) ON CONFLICT(workspace_id) DO UPDATE SET body=excluded.body",
            parameters,
        )

    @staticmethod
    def listed_workspaces_select_workspaces(db, parameters=()):
        return execute(
            db, "SELECT w.id,w.name,w.description,w.creator FROM workspaces w ORDER BY w._insert_order", parameters
        )

    @staticmethod
    def listed_workspaces_select_memberships(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM memberships WHERE user_id=:p0", parameters)

    @staticmethod
    def listed_workspaces_select_join_requests(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM join_requests WHERE user_id=:p0 AND status='PENDING'", parameters)

    @staticmethod
    def ask_to_join_insert_join_requests(db, parameters=()):
        return execute(
            db,
            "INSERT INTO join_requests(id,workspace_id,user_id,status,created)  VALUES (:p0,:p1,:p2,:p3,:p4)",
            parameters,
        )

    @staticmethod
    def ask_to_join_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def ask_to_join_select_workspaces(db, parameters=()):
        return execute(db, "SELECT 1 FROM workspaces WHERE id=:p0", parameters)

    @staticmethod
    def join_requests_select_join_requests(db, parameters=()):
        return execute(
            db,
            "SELECT j.id,j.workspace_id,j.user_id,j.status,j.created,u.profile FROM join_requests j JOIN users u ON u.id=j.user_id WHERE j.workspace_id=:p0 AND j.status='PENDING' ORDER BY j._insert_order",
            parameters,
        )

    @staticmethod
    def decide_join_update_join_requests(db, parameters=()):
        return execute(db, "UPDATE join_requests SET status=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def decide_join_insert_memberships(db, parameters=()):
        return execute(
            db,
            "INSERT INTO memberships(workspace_id,user_id,role)  VALUES (:p0,:p1,:p2) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def decide_join_select_join_requests(db, parameters=()):
        return execute(
            db,
            "SELECT id,workspace_id,user_id,status,created FROM join_requests WHERE id=:p0 AND workspace_id=:p1",
            parameters,
        )

    @staticmethod
    def invitations_select_invitations(db, parameters=()):
        return execute(
            db,
            "SELECT i.*,w.name FROM invitations i JOIN workspaces w ON w.id=i.workspace_id WHERE i.user_id=:p0 AND i.status='PENDING'",
            parameters,
        )

    @staticmethod
    def accept_insert_memberships(db, parameters=()):
        return execute(
            db,
            "INSERT INTO memberships(workspace_id,user_id,role)  VALUES (:p0,:p1,:p2) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def accept_update_invitations(db, parameters=()):
        return execute(db, "UPDATE invitations SET status='ACCEPTED' WHERE id=:p0", parameters)

    @staticmethod
    def accept_select_invitations(db, parameters=()):
        return execute(db, "SELECT * FROM invitations WHERE id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def member_change_update_memberships(db, parameters=()):
        return execute(db, "UPDATE memberships SET role=:p0 WHERE workspace_id=:p1 AND user_id=:p2", parameters)

    @staticmethod
    def member_change_delete_memberships(db, parameters=()):
        return execute(db, "DELETE FROM memberships WHERE workspace_id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def member_change_update_invitations(db, parameters=()):
        return execute(
            db,
            "UPDATE invitations SET status='REVOKED' WHERE workspace_id=:p0 AND user_id=:p1 AND status='PENDING'",
            parameters,
        )

    @staticmethod
    def member_change_select_memberships(db, parameters=()):
        return execute(db, "SELECT role FROM memberships WHERE workspace_id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def member_change_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE owner=:p0 AND workspace_id=:p1", parameters)

    @staticmethod
    def member_change_select_memberships_2(db, parameters=()):
        return execute(
            db,
            f"SELECT count(*) FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=:p0 AND m.role='ADMIN' AND m.user_id<>:p1 AND {json_text(db, 'u.profile', 'accountStatus')}='ACTIVE'",
            parameters,
        )

    @staticmethod
    def state_workspaces_select_workspaces(db, parameters=()):
        return execute(
            db,
            "SELECT w.id,w.name,w.description,w.creator,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=:p0 ORDER BY w._insert_order",
            parameters,
        )
