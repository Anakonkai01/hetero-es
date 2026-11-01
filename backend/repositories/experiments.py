"""Experiments SQL; transaction ownership is separate."""

from .base import execute


class ExperimentsRepository:
    @staticmethod
    def submit_insert_queue(db, parameters=()):
        return execute(db, "INSERT INTO queue(run_id) VALUES (?)", parameters)

    @staticmethod
    def cancel_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=?", parameters)

    @staticmethod
    def resume_insert_queue(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO queue(run_id) VALUES (?)", parameters)

    @staticmethod
    def resume_select_assignments(db, parameters=()):
        return execute(
            db, "SELECT released,snapshot FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters
        )

    @staticmethod
    def backup_policy_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT id,coordinator,epoch,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1",
            parameters,
        )

    @staticmethod
    def state_cancel_selected_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments", parameters)

    @staticmethod
    def state_cancel_selected_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=?", parameters)

    @staticmethod
    def state_cancel_selected_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id FROM devices WHERE id=?", parameters)

    @staticmethod
    def state_cancel_owned_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments WHERE owner=?", parameters)

    @staticmethod
    def state_cancel_owned_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=?", parameters)

    @staticmethod
    def state_eligibility_select_users(db, parameters=()):
        return execute(db, "SELECT profile FROM users WHERE id=?", parameters)

    @staticmethod
    def state_eligibility_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE workspace_id=?", parameters)

    @staticmethod
    def state_eligibility_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id,status,owner FROM devices WHERE id=?", parameters)

    @staticmethod
    def state_eligibility_select_devices_2(db, parameters=(), *, workers):
        return execute(
            db,
            "SELECT owner,status FROM devices WHERE worker_id IN (" + ",".join(("?" for _ in workers)) + ")",
            parameters,
        )

    @staticmethod
    def state_eligibility_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def state_get_select_experiments(db, parameters=()):
        return execute(db, "SELECT body,snapshot FROM experiments WHERE id=?", parameters)

    @staticmethod
    def state_list_select_experiments(db, parameters=()):
        return execute(db, "SELECT body,snapshot FROM experiments ORDER BY rowid", parameters)

    @staticmethod
    def state_save_update_experiments(db, parameters=()):
        return execute(db, "UPDATE experiments SET body=? WHERE id=?", parameters)

    @staticmethod
    def state_create_insert_experiments(db, parameters=()):
        return execute(db, "INSERT INTO experiments VALUES (?,?,?,NULL)", parameters)

    @staticmethod
    def state_snapshot_select_experiments(db, parameters=()):
        return execute(db, "SELECT snapshot FROM experiments WHERE id=?", parameters)

    @staticmethod
    def queue_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments", parameters)

    @staticmethod
    def queue_select_queue(db, parameters=()):
        return execute(db, "SELECT run_id FROM queue ORDER BY sequence", parameters)
