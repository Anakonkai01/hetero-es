"""Operations SQL; transaction ownership is separate."""

from .base import execute


class OperationsRepository:
    @staticmethod
    def users_select_users(db, parameters=()):
        return execute(db, "SELECT profile FROM users ORDER BY _insert_order", parameters)

    @staticmethod
    def edit_account_update_users(db, parameters=()):
        return execute(db, "UPDATE users SET profile=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def edit_account_delete_sessions(db, parameters=()):
        return execute(db, "DELETE FROM sessions WHERE user_id=:p0", parameters)

    @staticmethod
    def edit_account_select_users(db, parameters=()):
        return execute(db, "SELECT profile FROM users WHERE id<>:p0", parameters)

    @staticmethod
    def edit_account_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE owner=:p0", parameters)

    @staticmethod
    def revoke_sessions_delete_sessions(db, parameters=()):
        return execute(db, "DELETE FROM sessions WHERE user_id=:p0", parameters)

    @staticmethod
    def platform_audit_select_audit(db, parameters=()):
        return execute(
            db, "SELECT * FROM audit WHERE workspace_id IS NULL ORDER BY sequence DESC LIMIT 200", parameters
        )

    @staticmethod
    def operations_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key='metadataBackupStatus'", parameters)

    @staticmethod
    def operations_select_queue(db, parameters=()):
        return execute(db, "SELECT count(*) FROM queue", parameters)

    @staticmethod
    def resume_update_settings(db, parameters=()):
        return execute(db, "UPDATE settings SET value='false' WHERE key='dispatchHold'", parameters)

    @staticmethod
    def resume_delete_settings(db, parameters=()):
        return execute(db, "DELETE FROM settings WHERE key IN ('maintenanceId','agentMaintenance')", parameters)
