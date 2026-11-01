"""Devices SQL; transaction ownership is separate."""

from .base import execute


class DevicesRepository:
    @staticmethod
    def authenticate_device_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE token_digest=?", parameters)

    @staticmethod
    def authenticate_device_select_assignments(db, parameters=()):
        return execute(db, "SELECT 1 FROM assignments WHERE coordinator=? AND released=0", parameters)

    @staticmethod
    def pairing_insert_pairing_codes(db, parameters=()):
        return execute(db, "INSERT INTO pairing_codes VALUES (?,?,?,0)", parameters)

    @staticmethod
    def enroll_insert_devices(db, parameters=()):
        return execute(
            db,
            "INSERT INTO devices(id,worker_id,owner,name,token_digest,status,compute_url,bulk_url,self_test) VALUES (?,?,?,?,?,?,?,?,?)",
            parameters,
        )

    @staticmethod
    def enroll_update_pairing_codes(db, parameters=()):
        return execute(db, "UPDATE pairing_codes SET used=1 WHERE digest=?", parameters)

    @staticmethod
    def enroll_insert_worker_assignments(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO worker_assignments VALUES (?,?,NULL)", parameters)

    @staticmethod
    def enroll_select_pairing_codes(db, parameters=()):
        return execute(db, "SELECT * FROM pairing_codes WHERE digest=?", parameters)

    @staticmethod
    def enroll_select_devices(db, parameters=()):
        return execute(db, "SELECT 1 FROM devices WHERE worker_id=?", parameters)

    @staticmethod
    def enroll_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT owner FROM worker_assignments WHERE worker_id=?", parameters)

    @staticmethod
    def update_endpoints_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET compute_url=?,bulk_url=? WHERE id=?", parameters)

    @staticmethod
    def update_endpoints_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET self_test=? WHERE id=?", parameters)

    @staticmethod
    def update_endpoints_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=? AND owner=?", parameters)

    @staticmethod
    def qualification_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET self_test=? WHERE id=?", parameters)

    @staticmethod
    def qualification_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def devices_select_memberships(db, parameters=()):
        return execute(
            db,
            "SELECT m.user_id,w.id,w.name FROM memberships m JOIN workspaces w ON w.id=m.workspace_id ORDER BY w.rowid",
            parameters,
        )

    @staticmethod
    def approve_update_devices(db, parameters=()):
        return execute(db, 'UPDATE devices SET status="APPROVED" WHERE id=?', parameters)

    @staticmethod
    def approve_update_worker_assignments(db, parameters=()):
        return execute(db, "UPDATE worker_assignments SET workspace_id=? WHERE worker_id=?", parameters)

    @staticmethod
    def approve_update_devices_2(db, parameters=()):
        return execute(db, 'UPDATE devices SET status="REVOKED",enabled=0,desired=0 WHERE id=?', parameters)

    @staticmethod
    def approve_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def approve_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?",
            parameters,
        )

    @staticmethod
    def approve_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?", parameters)

    @staticmethod
    def remove_delete_devices(db, parameters=()):
        return execute(db, "DELETE FROM devices WHERE id=?", parameters)

    @staticmethod
    def remove_delete_value(db, parameters=(), *, table):
        return execute(db, f"DELETE FROM {table} WHERE device_id=?", parameters)

    @staticmethod
    def remove_delete_worker_assignments(db, parameters=()):
        return execute(db, "DELETE FROM worker_assignments WHERE worker_id=?", parameters)

    @staticmethod
    def remove_select_devices(db, parameters=()):
        return execute(db, "SELECT 1 FROM devices WHERE worker_id=?", parameters)

    @staticmethod
    def remove_device_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def managed_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def rename_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET name=? WHERE id=?", parameters)

    @staticmethod
    def delete_device_update_devices(db, parameters=()):
        return execute(db, 'UPDATE devices SET status="REVOKED",enabled=0,desired=0 WHERE id=?', parameters)

    @staticmethod
    def set_contribution_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET desired=? WHERE id=?", parameters)

    @staticmethod
    def set_contribution_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET keep_on=? WHERE id=?", parameters)

    @staticmethod
    def set_contribution_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?",
            parameters,
        )

    @staticmethod
    def contribution_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=? AND owner=?", parameters)

    @staticmethod
    def contribution_preference_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET keep_on=? WHERE id=?", parameters)

    @staticmethod
    def contribution_preference_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=? AND owner=?", parameters)

    @staticmethod
    def own_contribution_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def own_name_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET name=? WHERE id=?", parameters)

    @staticmethod
    def forget_self_update_devices(db, parameters=()):
        return execute(db, 'UPDATE devices SET status="REVOKED",enabled=0,desired=0,keep_on=0 WHERE id=?', parameters)

    @staticmethod
    def forget_self_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def own_summary_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id,a.coordinator,a.snapshot FROM assignments a JOIN device_reservations r ON r.assignment_id=a.id WHERE r.device_id=? AND a.released=0",
            parameters,
        )

    @staticmethod
    def own_summary_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def devices_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices ORDER BY rowid", parameters)

    @staticmethod
    def devices_select_device_reservations(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM device_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.device_id=?",
            parameters,
        )

    @staticmethod
    def devices_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM worker_assignments WHERE worker_id=?", parameters)

    @staticmethod
    def devices_select_model_probe_reservations(db, parameters=()):
        return execute(db, "SELECT job_id FROM model_probe_reservations WHERE device_id=? OR resource_id=?", parameters)

    @staticmethod
    def snapshot_select_assignments(db, parameters=()):
        return execute(
            db, "SELECT snapshot,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters
        )

    @staticmethod
    def runs_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments ORDER BY rowid", parameters)

    @staticmethod
    def devices_select_physical_reservations(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.resource_id=?",
            parameters,
        )

    @staticmethod
    def devices_select_experiments(db, parameters=()):
        return execute(db, "SELECT snapshot FROM experiments WHERE id=?", parameters)

    @staticmethod
    def devices_select_device_telemetry_history(db, parameters=()):
        return execute(
            db,
            "SELECT body FROM device_telemetry_history WHERE device_id=? ORDER BY received_at DESC LIMIT 60",
            parameters,
        )
