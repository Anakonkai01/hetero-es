"""Experiments SQL; transaction ownership is separate."""

from ..db.dialect import bind_list
from .base import execute


class ExperimentsRepository:
    @staticmethod
    def submit_insert_queue(db, parameters=()):
        return execute(db, "INSERT INTO queue(run_id) VALUES (:p0)", parameters)

    @staticmethod
    def cancel_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)

    @staticmethod
    def resume_insert_queue(db, parameters=()):
        return execute(db, "INSERT INTO queue(run_id) VALUES (:p0) ON CONFLICT DO NOTHING", parameters)

    @staticmethod
    def resume_select_assignments(db, parameters=()):
        return execute(
            db, "SELECT released,snapshot FROM assignments WHERE run_id=:p0 ORDER BY epoch DESC LIMIT 1", parameters
        )

    @staticmethod
    def backup_policy_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT id,coordinator,epoch,released FROM assignments WHERE run_id=:p0 ORDER BY epoch DESC LIMIT 1",
            parameters,
        )

    @staticmethod
    def state_cancel_selected_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments", parameters)

    @staticmethod
    def state_cancel_selected_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)

    @staticmethod
    def state_cancel_selected_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id FROM devices WHERE id=:p0", parameters)

    @staticmethod
    def state_cancel_owned_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments WHERE owner=:p0", parameters)

    @staticmethod
    def state_cancel_owned_delete_queue(db, parameters=()):
        return execute(db, "DELETE FROM queue WHERE run_id=:p0", parameters)

    @staticmethod
    def state_eligibility_select_users(db, parameters=()):
        return execute(db, "SELECT profile FROM users WHERE id=:p0", parameters)

    @staticmethod
    def state_eligibility_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE workspace_id=:p0", parameters)

    @staticmethod
    def state_eligibility_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id,status,owner FROM devices WHERE id=:p0", parameters)

    @staticmethod
    def state_eligibility_select_devices_2(db, parameters=(), *, workers):
        return execute(
            db, "SELECT owner,status FROM devices WHERE worker_id IN (" + bind_list(workers) + ")", parameters
        )

    @staticmethod
    def state_eligibility_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def state_get_select_experiments(db, parameters=()):
        return execute(db, "SELECT body,snapshot FROM experiments WHERE id=:p0", parameters)

    @staticmethod
    def state_list_select_experiments(db, parameters=()):
        return execute(db, "SELECT body,snapshot FROM experiments ORDER BY _insert_order", parameters)

    @staticmethod
    def state_save_update_experiments(db, parameters=()):
        return execute(db, "UPDATE experiments SET body=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def state_create_insert_experiments(db, parameters=()):
        return execute(db, "INSERT INTO experiments(id,owner,body,snapshot)  VALUES (:p0,:p1,:p2,NULL)", parameters)

    @staticmethod
    def state_snapshot_select_experiments(db, parameters=()):
        return execute(db, "SELECT snapshot FROM experiments WHERE id=:p0", parameters)

    @staticmethod
    def queue_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments", parameters)

    @staticmethod
    def queue_select_queue(db, parameters=()):
        return execute(db, "SELECT run_id FROM queue ORDER BY sequence", parameters)
