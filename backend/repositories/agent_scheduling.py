"""AgentScheduling SQL; business decisions stay in the service mixin."""

from .base import execute


class AgentSchedulingRepository:
    @staticmethod
    def waiting_reason_select_device_reservations(db, parameters=()):
        return execute(
            db, "SELECT d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id", parameters
        )

    @staticmethod
    def waiting_reason_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key=?", parameters)

    @staticmethod
    def waiting_reason_select_physical_reservations(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE resource_id=?",
            parameters,
        )

    @staticmethod
    def intended_members_select_assignment_members(db, parameters=()):
        return execute(db, "SELECT worker_id, action FROM assignment_members WHERE run_id=? ORDER BY rowid", parameters)

    @staticmethod
    def change_members_insert_assignment_members(db, parameters=()):
        return execute(db, "INSERT INTO assignment_members VALUES (?,?,?,?,?,?,?)", parameters)

    @staticmethod
    def change_members_update_assignments(db, parameters=()):
        return execute(db, "UPDATE assignments SET body=? WHERE id=?", parameters)

    @staticmethod
    def change_members_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters)

    @staticmethod
    def change_members_insert_device_reservations(db, parameters=()):
        return execute(db, "INSERT INTO device_reservations VALUES (?,?)", parameters)

    @staticmethod
    def change_members_select_device_reservations(db, parameters=()):
        return execute(db, "SELECT assignment_id FROM device_reservations WHERE device_id=?", parameters)

    @staticmethod
    def change_members_insert_physical_reservations(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO physical_reservations VALUES (?,?)", parameters)

    @staticmethod
    def note_membership_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments WHERE id=?", parameters)

    @staticmethod
    def auto_join_select_assignment_members(db, parameters=()):
        return execute(db, "SELECT worker_id FROM assignment_members WHERE run_id=? AND action='LEAVE'", parameters)

    @staticmethod
    def auto_join_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE workspace_id=?", parameters)

    @staticmethod
    def leave_on_disable_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=? AND a.released=0 AND a.coordinator!=?",
            parameters,
        )

    @staticmethod
    def release_left_members_delete_device_reservations(db, parameters=()):
        return execute(db, "DELETE FROM device_reservations WHERE device_id=? AND assignment_id=?", parameters)

    @staticmethod
    def release_left_members_update_assignments(db, parameters=()):
        return execute(db, "UPDATE assignments SET body=? WHERE id=?", parameters)

    @staticmethod
    def release_left_members_select_experiments(db, parameters=()):
        return execute(db, "SELECT body FROM experiments WHERE id=?", parameters)

    @staticmethod
    def release_left_members_delete_physical_reservations(db, parameters=()):
        return execute(db, "DELETE FROM physical_reservations WHERE resource_id=? AND assignment_id=?", parameters)

    @staticmethod
    def release_left_members_select_devices(db, parameters=()):
        return execute(db, "SELECT self_test,seen FROM devices WHERE id=?", parameters)

    @staticmethod
    def reservations_select_device_reservations(db, parameters=()):
        return execute(db, "SELECT * FROM device_reservations", parameters)

    @staticmethod
    def _assignment_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE id=?", parameters)

    @staticmethod
    def submit_insert_assignments(db, parameters=()):
        return execute(db, "INSERT INTO assignments VALUES (?,?,?,?,?,?,0)", parameters)

    @staticmethod
    def submit_insert_device_reservations(db, parameters=()):
        return execute(db, "INSERT INTO device_reservations VALUES (?,?)", parameters)

    @staticmethod
    def submit_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters)

    @staticmethod
    def submit_insert_physical_reservations(db, parameters=()):
        return execute(db, "INSERT INTO physical_reservations VALUES (?,?)", parameters)

    @staticmethod
    def cancel_select_assignments(db, parameters=()):
        return execute(
            db, "SELECT id,body,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters
        )

    @staticmethod
    def pause_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters)

    @staticmethod
    def _release_confirmed_update_assignments(db, parameters=()):
        return execute(db, "UPDATE assignments SET released=1 WHERE id=?", parameters)

    @staticmethod
    def _release_confirmed_delete_device_reservations(db, parameters=()):
        return execute(db, "DELETE FROM device_reservations WHERE assignment_id=?", parameters)

    @staticmethod
    def _release_confirmed_delete_physical_reservations(db, parameters=()):
        return execute(db, "DELETE FROM physical_reservations WHERE assignment_id=?", parameters)

    @staticmethod
    def _release_confirmed_update_assignments_2(db, parameters=()):
        return execute(db, "UPDATE assignments SET snapshot=? WHERE id=?", parameters)

    @staticmethod
    def _release_confirmed_select_devices(db, parameters=()):
        return execute(db, "SELECT processes,seen FROM devices WHERE id=?", parameters)
