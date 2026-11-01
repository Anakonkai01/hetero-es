"""Model_Qualification SQL; transaction ownership is separate."""

from .base import execute


class ModelQualificationRepository:
    @staticmethod
    def status_select_model_probe_jobs(db, parameters=()):
        return execute(
            db, "SELECT body FROM model_probe_jobs WHERE asset_id=:p0 ORDER BY _insert_order DESC", parameters
        )

    @staticmethod
    def cancel_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE id=:p0 AND asset_id=:p1", parameters)

    @staticmethod
    def transfer_select_model_probe_jobs(db, parameters=()):
        return execute(
            db,
            "SELECT j.body FROM model_probe_jobs j JOIN model_probe_reservations r ON r.job_id=j.id WHERE j.id=:p0 AND j.device_id=:p1",
            parameters,
        )

    @staticmethod
    def save_update_model_probe_jobs(db, parameters=()):
        return execute(db, "UPDATE model_probe_jobs SET body=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def effective_profile_select_value(db, parameters=(), *, engine_clause, engine_column, references, table):
        return execute(
            db,
            f"SELECT q.manifest_hash,{engine_column} FROM {table} q JOIN {references} r ON r.workspace_id=q.workspace_id AND r.manifest_hash=q.manifest_hash AND r.reference_hash=q.reference_hash"
            + engine_clause
            + " WHERE q.device_id=:p0 AND q.workspace_id=:p1 AND q.profile_hash=:p2",
            parameters,
        )

    @staticmethod
    def start_insert_model_probe_jobs(db, parameters=()):
        return execute(
            db,
            "INSERT INTO model_probe_jobs(id,workspace_id,asset_id,device_id,body)  VALUES (:p0,:p1,:p2,:p3,:p4)",
            parameters,
        )

    @staticmethod
    def start_insert_model_probe_reservations(db, parameters=()):
        return execute(
            db, "INSERT INTO model_probe_reservations(job_id,device_id,resource_id)  VALUES (:p0,:p1,:p2)", parameters
        )

    @staticmethod
    def accept_delete_model_probe_reservations(db, parameters=()):
        return execute(db, "DELETE FROM model_probe_reservations WHERE job_id=:p0", parameters)

    @staticmethod
    def reference_select_model_engine_references(db, parameters=()):
        return execute(
            db,
            "SELECT * FROM model_engine_references WHERE workspace_id=:p0 AND manifest_hash=:p1 AND engine=:p2",
            parameters,
        )

    @staticmethod
    def start_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE workspace_id=:p0", parameters)

    @staticmethod
    def accept_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def accept_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM worker_assignments WHERE worker_id=:p0", parameters)

    @staticmethod
    def accept_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE device_id=:p0", parameters)

    @staticmethod
    def accept_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status='QUARANTINED',enabled=0,desired=0 WHERE id=:p0", parameters)

    @staticmethod
    def reference_select_model_references(db, parameters=()):
        return execute(db, "SELECT * FROM model_references WHERE workspace_id=:p0 AND manifest_hash=:p1", parameters)

    @staticmethod
    def start_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def accept_select_model_probe_jobs_2(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE id=:p0 AND device_id=:p1", parameters)

    @staticmethod
    def start_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM worker_assignments WHERE worker_id=:p0", parameters)

    @staticmethod
    def start_select_device_reservations(db, parameters=()):
        return execute(
            db, "SELECT d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id", parameters
        )

    @staticmethod
    def accept_insert_model_references(db, parameters=(), *, engine_args):
        return execute(
            db,
            "INSERT INTO model_references(workspace_id,manifest_hash,reference_hash,body)  VALUES (:p0,:p1,:p2,:p3) ON CONFLICT DO NOTHING"
            if not engine_args
            else "INSERT INTO model_engine_references(workspace_id,manifest_hash,reference_hash,body,engine)  VALUES (:p0,:p1,:p2,:p3,:p4) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def accept_insert_model_qualifications(db, parameters=(), *, engine_args):
        return execute(
            db,
            "INSERT INTO model_qualifications(device_id,workspace_id,manifest_hash,profile_hash,reference_hash,body)  VALUES (:p0,:p1,:p2,:p3,:p4,:p5) ON CONFLICT(device_id,workspace_id,manifest_hash) DO UPDATE SET profile_hash=excluded.profile_hash,reference_hash=excluded.reference_hash,body=excluded.body"
            if not engine_args
            else "INSERT INTO model_engine_qualifications(device_id,workspace_id,manifest_hash,profile_hash,reference_hash,body,engine)  VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6) ON CONFLICT(device_id,workspace_id,manifest_hash,engine) DO UPDATE SET profile_hash=excluded.profile_hash,reference_hash=excluded.reference_hash,body=excluded.body",
            parameters,
        )
