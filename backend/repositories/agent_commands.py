"""AgentCommands SQL; business decisions stay in the service mixin."""

from .base import execute


class AgentCommandsRepository:
    @staticmethod
    def enqueue_insert_device_commands(db, parameters=()):
        return execute(
            db,
            "INSERT INTO device_commands(id,device_id,dedupe,body,ack,created)  VALUES (:p0,:p1,:p2,:p3,0,:p4) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def require_command_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key=:p0", parameters)

    @staticmethod
    def commands_select_device_commands(db, parameters=()):
        return execute(
            db, "SELECT body FROM device_commands WHERE device_id=:p0 AND ack=0 ORDER BY created", parameters
        )

    @staticmethod
    def commands_select_model_probe_jobs(db, parameters=()):
        return execute(db, "SELECT body FROM model_probe_jobs WHERE id=:p0", parameters)

    @staticmethod
    def commands_select_assignments(db, parameters=()):
        return execute(db, "SELECT released FROM assignments WHERE id=:p0 AND epoch=:p1", parameters)

    @staticmethod
    def worker_command_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )
