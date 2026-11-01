"""AgentCommands SQL; business decisions stay in the service mixin."""

from .base import execute


class AgentCommandsRepository:
    @staticmethod
    def enqueue_insert_device_commands(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO device_commands VALUES (?,?,?,?,0,?)", parameters)

    @staticmethod
    def require_command_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key=?", parameters)

    @staticmethod
    def commands_select_device_commands(db, parameters=()):
        return execute(db, "SELECT body FROM device_commands WHERE device_id=? AND ack=0 ORDER BY created", parameters)

    @staticmethod
    def commands_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE id=?", parameters)

    @staticmethod
    def commands_select_assignments(db, parameters=()):
        return execute(db, "SELECT released FROM assignments WHERE id=? AND epoch=?", parameters)

    @staticmethod
    def worker_command_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)
