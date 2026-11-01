"""DeviceStateRepository SQL."""

from .base import execute


class DeviceStateRepository:
    @staticmethod
    def ensure_workers_insert_settings(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO settings VALUES (?,?)", parameters)

    @staticmethod
    def ensure_workers_insert_worker_assignments(db, parameters=()):
        return execute(db, "INSERT INTO worker_assignments VALUES (?,?,?)", parameters)

    @staticmethod
    def ensure_workers_select_settings(db, parameters=()):
        return execute(db, 'SELECT value FROM settings WHERE key="workersInitialized"', parameters)

    @staticmethod
    def ensure_workers_select_workspaces(db, parameters=()):
        return execute(db, 'SELECT creator FROM workspaces WHERE id="lab"', parameters)

    @staticmethod
    def ensure_workers_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT 1 FROM worker_assignments WHERE worker_id=?", parameters)

    @staticmethod
    def assignments_select_worker_assignments(db, parameters=()):
        return execute(db, "SELECT worker_id FROM worker_assignments WHERE workspace_id=?", parameters)

    @staticmethod
    def device_names_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id,name FROM devices WHERE name<>''", parameters)

    @staticmethod
    def device_identities_select_devices(db, parameters=()):
        return execute(db, "SELECT worker_id,name,self_test FROM devices", parameters)
