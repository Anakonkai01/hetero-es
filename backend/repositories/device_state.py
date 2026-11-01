"""DeviceStateRepository SQL."""

from .base import execute


class DeviceStateRepository:
    @staticmethod
    def ensure_workers_insert_settings(db, parameters=()):
        return execute(db, "INSERT INTO settings(key,value)  VALUES (:p0,:p1) ON CONFLICT DO NOTHING", parameters)

    @staticmethod
    def ensure_workers_insert_worker_assignments(db, parameters=()):
        return execute(
            db, "INSERT INTO worker_assignments(worker_id,owner,workspace_id)  VALUES (:p0,:p1,:p2)", parameters
        )

    @staticmethod
    def ensure_workers_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key='workersInitialized'", parameters)

    @staticmethod
    def ensure_workers_select_workspaces(db, parameters=()):
        return execute(db, "SELECT creator FROM workspaces WHERE id='lab'", parameters)

    @staticmethod
    def ensure_workers_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT 1 FROM worker_assignments WHERE worker_id=:p0", parameters)

    @staticmethod
    def assignments_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE workspace_id=:p0", parameters)

    @staticmethod
    def device_names_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id,name FROM devices WHERE name<>''", parameters)

    @staticmethod
    def device_identities_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id,name,self_test FROM devices", parameters)
