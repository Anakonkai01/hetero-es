"""Model_Qualification SQL; transaction ownership is separate."""

from .base import execute


class ModelQualificationRepository:
    @staticmethod
    def status_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE asset_id=? ORDER BY rowid DESC", parameters)

    @staticmethod
    def cancel_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE id=? AND asset_id=?", parameters)

    @staticmethod
    def transfer_select_model_probe_jobs(db, parameters=()):
        return execute(
            db,
            "SELECT j.body FROM model_probe_jobs j JOIN model_probe_reservations r ON r.job_id=j.id WHERE j.id=? AND j.device_id=?",
            parameters,
        )

    @staticmethod
    def save_update_model_probe_jobs(db, parameters=()):
        return execute(db, "UPDATE model_probe_jobs SET body=? WHERE id=?", parameters)

    @staticmethod
    def effective_profile_select_value(db, parameters=(), *, engine_clause, engine_column, references, table):
        return execute(
            db,
            f"SELECT q.manifest_hash,{engine_column} FROM {table} q JOIN {references} r ON r.workspace_id=q.workspace_id AND r.manifest_hash=q.manifest_hash AND r.reference_hash=q.reference_hash"
            + engine_clause
            + " WHERE q.device_id=? AND q.workspace_id=? AND q.profile_hash=?",
            parameters,
        )

    @staticmethod
    def start_insert_model_probe_jobs(db, parameters=()):
        return execute(db, "INSERT INTO model_probe_jobs VALUES (?,?,?,?,?)", parameters)

    @staticmethod
    def start_insert_model_probe_reservations(db, parameters=()):
        return execute(db, "INSERT INTO model_probe_reservations VALUES (?,?,?)", parameters)

    @staticmethod
    def accept_delete_model_probe_reservations(db, parameters=()):
        return execute(db, "DELETE FROM model_probe_reservations WHERE job_id=?", parameters)

    @staticmethod
    def reference_select_model_engine_references(db, parameters=()):
        return execute(
            db,
            "SELECT * FROM model_engine_references WHERE workspace_id=? AND manifest_hash=? AND engine=?",
            parameters,
        )

    @staticmethod
    def start_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE workspace_id=?", parameters)

    @staticmethod
    def accept_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def accept_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM worker_assignments WHERE worker_id=?", parameters)

    @staticmethod
    def accept_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE device_id=?", parameters)

    @staticmethod
    def accept_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status='QUARANTINED',enabled=0,desired=0 WHERE id=?", parameters)

    @staticmethod
    def reference_select_model_references(db, parameters=()):
        return execute(db, "SELECT * FROM model_references WHERE workspace_id=? AND manifest_hash=?", parameters)

    @staticmethod
    def start_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def accept_select_model_probe_jobs_2(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE id=? AND device_id=?", parameters)

    @staticmethod
    def start_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT workspace_id FROM worker_assignments WHERE worker_id=?", parameters)

    @staticmethod
    def start_select_device_reservations(db, parameters=()):
        return execute(
            db, "SELECT d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id", parameters
        )

    @staticmethod
    def accept_insert_model_references(db, parameters=(), *, engine_args):
        return execute(
            db,
            "INSERT OR IGNORE INTO model_references VALUES (?,?,?,?)"
            if not engine_args
            else "INSERT OR IGNORE INTO model_engine_references VALUES (?,?,?,?,?)",
            parameters,
        )

    @staticmethod
    def accept_insert_model_qualifications(db, parameters=(), *, engine_args):
        return execute(
            db,
            "INSERT OR REPLACE INTO model_qualifications VALUES (?,?,?,?,?,?)"
            if not engine_args
            else "INSERT OR REPLACE INTO model_engine_qualifications VALUES (?,?,?,?,?,?,?)",
            parameters,
        )
