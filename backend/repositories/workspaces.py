"""Workspace SQL; transaction boundaries belong to business operations."""

from .base import execute


class WorkspacesRepository:
    @staticmethod
    def create_workspace_insert_workspaces(db, parameters=()):
        return execute(db, "INSERT INTO workspaces VALUES (?,?,?,?)", parameters)

    @staticmethod
    def create_workspace_insert_memberships(db, parameters=()):
        return execute(db, "INSERT INTO memberships VALUES (?,?,?)", parameters)

    @staticmethod
    def invite_insert_invitations(db, parameters=()):
        return execute(db, "INSERT INTO invitations VALUES (?,?,?,?,?)", parameters)

    @staticmethod
    def invite_select_users(db, parameters=()):
        return execute(db, "SELECT id,profile FROM users WHERE json_extract(profile,'$.username')=?", parameters)

    @staticmethod
    def invite_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def coordinator_devices_select_devices(db, parameters=()):
        return execute(
            db,
            'SELECT d.id,d.self_test FROM devices d JOIN worker_assignments a ON a.worker_id=d.worker_id WHERE d.status="APPROVED" AND a.workspace_id=?',
            parameters,
        )

    @staticmethod
    def settings_select_workspace_settings(db, parameters=()):
        return execute(db, "SELECT body FROM workspace_settings WHERE workspace_id=?", parameters)

    @staticmethod
    def save_settings_insert_workspace_settings(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO workspace_settings VALUES (?,?)", parameters)

    @staticmethod
    def listed_workspaces_select_workspaces(db, parameters=()):
        return execute(db, "SELECT w.* FROM workspaces w ORDER BY w.rowid", parameters)

    @staticmethod
    def listed_workspaces_select_memberships(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM memberships WHERE user_id=?", parameters)

    @staticmethod
    def listed_workspaces_select_join_requests(db, parameters=()):
        return execute(db, 'SELECT workspace_id FROM join_requests WHERE user_id=? AND status="PENDING"', parameters)

    @staticmethod
    def ask_to_join_insert_join_requests(db, parameters=()):
        return execute(db, "INSERT INTO join_requests VALUES (?,?,?,?,?)", parameters)

    @staticmethod
    def ask_to_join_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def ask_to_join_select_workspaces(db, parameters=()):
        return execute(db, "SELECT 1 FROM workspaces WHERE id=?", parameters)

    @staticmethod
    def join_requests_select_join_requests(db, parameters=()):
        return execute(
            db,
            'SELECT j.*,u.profile FROM join_requests j JOIN users u ON u.id=j.user_id WHERE j.workspace_id=? AND j.status="PENDING" ORDER BY j.rowid',
            parameters,
        )

    @staticmethod
    def decide_join_update_join_requests(db, parameters=()):
        return execute(db, "UPDATE join_requests SET status=? WHERE id=?", parameters)

    @staticmethod
    def decide_join_insert_memberships(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO memberships VALUES (?,?,?)", parameters)

    @staticmethod
    def decide_join_select_join_requests(db, parameters=()):
        return execute(db, "SELECT * FROM join_requests WHERE id=? AND workspace_id=?", parameters)

    @staticmethod
    def invitations_select_invitations(db, parameters=()):
        return execute(
            db,
            'SELECT i.*,w.name FROM invitations i JOIN workspaces w ON w.id=i.workspace_id WHERE i.user_id=? AND i.status="PENDING"',
            parameters,
        )

    @staticmethod
    def accept_insert_memberships(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO memberships VALUES (?,?,?)", parameters)

    @staticmethod
    def accept_update_invitations(db, parameters=()):
        return execute(db, 'UPDATE invitations SET status="ACCEPTED" WHERE id=?', parameters)

    @staticmethod
    def accept_select_invitations(db, parameters=()):
        return execute(db, "SELECT * FROM invitations WHERE id=? AND user_id=?", parameters)

    @staticmethod
    def member_change_update_memberships(db, parameters=()):
        return execute(db, "UPDATE memberships SET role=? WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def member_change_delete_memberships(db, parameters=()):
        return execute(db, "DELETE FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def member_change_update_invitations(db, parameters=()):
        return execute(
            db,
            'UPDATE invitations SET status="REVOKED" WHERE workspace_id=? AND user_id=? AND status="PENDING"',
            parameters,
        )

    @staticmethod
    def member_change_select_memberships(db, parameters=()):
        return execute(db, "SELECT role FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def member_change_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE owner=? AND workspace_id=?", parameters)

    @staticmethod
    def member_change_select_memberships_2(db, parameters=()):
        return execute(
            db,
            "SELECT count(*) FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.workspace_id=? AND m.role='ADMIN' AND m.user_id<>? AND json_extract(u.profile,'$.accountStatus')='ACTIVE'",
            parameters,
        )

    @staticmethod
    def queue_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments", parameters)

    @staticmethod
    def queue_select_queue(db, parameters=()):
        return execute(db, "SELECT run_id FROM queue ORDER BY sequence", parameters)
