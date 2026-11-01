"""Devices SQL; transaction ownership is separate."""

from .base import execute


class DevicesRepository:
    @staticmethod
    def authenticate_device_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE token_digest=:p0",
            parameters,
        )

    @staticmethod
    def authenticate_device_select_assignments(db, parameters=()):
        return execute(db, "SELECT 1 FROM assignments WHERE coordinator=:p0 AND released=0", parameters)

    @staticmethod
    def pairing_insert_pairing_codes(db, parameters=()):
        return execute(db, "INSERT INTO pairing_codes(digest,owner,expires,used)  VALUES (:p0,:p1,:p2,0)", parameters)

    @staticmethod
    def enroll_insert_devices(db, parameters=()):
        return execute(
            db,
            "INSERT INTO devices(id,worker_id,owner,name,token_digest,status,compute_url,bulk_url,self_test) VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8)",
            parameters,
        )

    @staticmethod
    def enroll_update_pairing_codes(db, parameters=()):
        return execute(db, "UPDATE pairing_codes SET used=1 WHERE digest=:p0", parameters)

    @staticmethod
    def enroll_insert_worker_assignments(db, parameters=()):
        return execute(
            db,
            "INSERT INTO worker_assignments(worker_id,owner,workspace_id)  VALUES (:p0,:p1,NULL) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def enroll_select_pairing_codes(db, parameters=()):
        return execute(db, "SELECT * FROM pairing_codes WHERE digest=:p0", parameters)

    @staticmethod
    def enroll_select_devices(db, parameters=()):
        return execute(db, "SELECT 1 FROM devices WHERE worker_id=:p0", parameters)

    @staticmethod
    def enroll_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT owner FROM worker_assignments WHERE worker_id=:p0", parameters)

    @staticmethod
    def update_endpoints_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET compute_url=:p0,bulk_url=:p1 WHERE id=:p2", parameters)

    @staticmethod
    def update_endpoints_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET self_test=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def update_endpoints_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0 AND owner=:p1",
            parameters,
        )

    @staticmethod
    def qualification_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET self_test=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def qualification_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def devices_select_memberships(db, parameters=()):
        return execute(
            db,
            "SELECT m.user_id,w.id,w.name FROM memberships m JOIN workspaces w ON w.id=m.workspace_id ORDER BY w._insert_order",
            parameters,
        )

    @staticmethod
    def approve_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status='APPROVED' WHERE id=:p0", parameters)

    @staticmethod
    def approve_update_worker_assignments(db, parameters=()):
        return execute(db, "UPDATE worker_assignments SET workspace_id=:p0 WHERE worker_id=:p1", parameters)

    @staticmethod
    def approve_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET status='REVOKED',enabled=0,desired=0 WHERE id=:p0", parameters)

    @staticmethod
    def approve_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def approve_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=:p0",
            parameters,
        )

    @staticmethod
    def approve_select_memberships(db, parameters=()):
        return execute(db, "SELECT 1 FROM memberships WHERE workspace_id=:p0 AND user_id=:p1", parameters)

    @staticmethod
    def remove_delete_devices(db, parameters=()):
        return execute(db, "DELETE FROM devices WHERE id=:p0", parameters)

    @staticmethod
    def remove_delete_value(db, parameters=(), *, table):
        return execute(db, f"DELETE FROM {table} WHERE device_id=:p0", parameters)

    @staticmethod
    def remove_delete_worker_assignments(db, parameters=()):
        return execute(db, "DELETE FROM worker_assignments WHERE worker_id=:p0", parameters)

    @staticmethod
    def remove_select_devices(db, parameters=()):
        return execute(db, "SELECT 1 FROM devices WHERE worker_id=:p0", parameters)

    @staticmethod
    def remove_device_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def managed_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def rename_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET name=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def delete_device_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status='REVOKED',enabled=0,desired=0 WHERE id=:p0", parameters)

    @staticmethod
    def set_contribution_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET desired=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def set_contribution_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET keep_on=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def set_contribution_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=:p0",
            parameters,
        )

    @staticmethod
    def contribution_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0 AND owner=:p1",
            parameters,
        )

    @staticmethod
    def contribution_preference_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET keep_on=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def contribution_preference_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0 AND owner=:p1",
            parameters,
        )

    @staticmethod
    def own_contribution_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def own_name_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET name=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def forget_self_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status='REVOKED',enabled=0,desired=0,keep_on=0 WHERE id=:p0", parameters)

    @staticmethod
    def forget_self_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def own_summary_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id,a.coordinator,a.snapshot FROM assignments a JOIN device_reservations r ON r.assignment_id=a.id WHERE r.device_id=:p0 AND a.released=0",
            parameters,
        )

    @staticmethod
    def own_summary_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def devices_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices ORDER BY _insert_order",
            parameters,
        )

    @staticmethod
    def devices_select_device_reservations(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM device_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.device_id=:p0",
            parameters,
        )

    @staticmethod
    def devices_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM worker_assignments WHERE worker_id=:p0", parameters)

    @staticmethod
    def devices_select_model_probe_reservations(db, parameters=()):
        return execute(
            db, "SELECT job_id FROM model_probe_reservations WHERE device_id=:p0 OR resource_id=:p1", parameters
        )

    @staticmethod
    def snapshot_select_assignments(db, parameters=()):
        return execute(
            db, "SELECT snapshot,released FROM assignments WHERE run_id=:p0 ORDER BY epoch DESC LIMIT 1", parameters
        )

    @staticmethod
    def runs_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT id,run_id,coordinator,epoch,body,snapshot,released FROM assignments ORDER BY _insert_order",
            parameters,
        )

    @staticmethod
    def devices_select_physical_reservations(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE r.resource_id=:p0",
            parameters,
        )

    @staticmethod
    def devices_select_experiments(db, parameters=()):
        return execute(db, "SELECT snapshot FROM experiments WHERE id=:p0", parameters)

    @staticmethod
    def devices_select_device_telemetry_history(db, parameters=()):
        return execute(
            db,
            "SELECT body FROM device_telemetry_history WHERE device_id=:p0 ORDER BY received_at DESC LIMIT 60",
            parameters,
        )
