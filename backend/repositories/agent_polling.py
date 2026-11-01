"""AgentPolling SQL; business decisions stay in the service mixin."""

from .base import execute


class AgentPollingRepository:
    @staticmethod
    def poll_insert_settings(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES (?,?)", parameters)

    @staticmethod
    def poll_select_devices(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def poll_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE released=0", parameters)

    @staticmethod
    def poll_select_devices_2(db, parameters=()):
        return execute(db, "SELECT * FROM devices WHERE id=?", parameters)

    @staticmethod
    def poll_select_assignments_2(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE id=?", parameters)

    @staticmethod
    def poll_select_assignments_3(db, parameters=()):
        return execute(db, "SELECT id,body FROM assignments WHERE released=1", parameters)

    @staticmethod
    def poll_select_assignments_4(db, parameters=()):
        return execute(db, "SELECT 1 FROM assignments WHERE id=?", parameters)

    @staticmethod
    def poll_select_device_reservations(db, parameters=()):
        return execute(db, "SELECT 1 FROM device_reservations WHERE device_id=? AND assignment_id=?", parameters)

    @staticmethod
    def _refresh_observation_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET self_test=? WHERE id=?", parameters)

    @staticmethod
    def _refresh_observation_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET telemetry=? WHERE id=?", parameters)

    @staticmethod
    def _refresh_observation_insert_device_telemetry_history(db, parameters=()):
        return execute(db, "INSERT OR IGNORE INTO device_telemetry_history VALUES (?,?,?,?,?)", parameters)

    @staticmethod
    def _refresh_observation_delete_device_telemetry_history(db, parameters=()):
        return execute(
            db,
            "DELETE FROM device_telemetry_history WHERE device_id=? AND rowid NOT IN (SELECT rowid FROM device_telemetry_history WHERE device_id=? ORDER BY received_at DESC LIMIT 180)",
            parameters,
        )

    @staticmethod
    def _refresh_observation_update_devices_3(db, parameters=()):
        return execute(db, "UPDATE devices SET telemetry=NULL WHERE id=?", parameters)

    @staticmethod
    def _update_boot_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET boot_id=?,seen=?,enabled=?,desired=?,processes=? WHERE id=?", parameters)

    @staticmethod
    def _update_boot_update_device_commands(db, parameters=()):
        return execute(
            db,
            "UPDATE device_commands SET ack=1 WHERE device_id=? AND json_extract(body,'$.kind')='SET_CONTRIBUTION'",
            parameters,
        )

    @staticmethod
    def _update_boot_update_device_commands_2(db, parameters=()):
        return execute(db, "UPDATE device_commands SET ack=1 WHERE id=? AND device_id=?", parameters)

    @staticmethod
    def _update_boot_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.* FROM assignments a JOIN device_reservations r ON r.assignment_id=a.id WHERE r.device_id=?",
            parameters,
        )

    @staticmethod
    def _quarantine_processes_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status=?,enabled=0,desired=0 WHERE id=?", parameters)

    @staticmethod
    def _quarantine_processes_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?",
            parameters,
        )

    @staticmethod
    def _accept_events_select_assignments(db, parameters=()):
        return execute(db, "SELECT coordinator,epoch FROM assignments WHERE id=?", parameters)

    @staticmethod
    def _accept_events_insert_monitoring_events(db, parameters=()):
        return execute(
            db, "INSERT OR IGNORE INTO monitoring_events(event_id,assignment_id,body) VALUES (?,?,?)", parameters
        )

    @staticmethod
    def _accept_events_select_assignments_2(db, parameters=()):
        return execute(db, "SELECT body,released FROM assignments WHERE id=?", parameters)

    @staticmethod
    def _accept_events_update_devices(db, parameters=()):
        return execute(
            db,
            "UPDATE devices SET status='QUARANTINED',enabled=0,desired=0 WHERE id=? AND status='APPROVED'",
            parameters,
        )

    @staticmethod
    def _accept_reports_insert_device_reports(db, parameters=()):
        return execute(db, "INSERT INTO device_reports VALUES (?,?,?)", parameters)

    @staticmethod
    def _accept_reports_update_assignments(db, parameters=()):
        return execute(db, "UPDATE assignments SET snapshot=? WHERE id=?", parameters)

    @staticmethod
    def _accept_reports_select_assignments(db, parameters=()):
        return execute(db, "SELECT * FROM assignments WHERE id=?", parameters)

    @staticmethod
    def _accept_reports_select_device_reports(db, parameters=()):
        return execute(
            db, "SELECT 1 FROM device_reports WHERE device_id=? AND assignment_id=? AND sequence=?", parameters
        )

    @staticmethod
    def _accept_reports_update_experiments(db, parameters=()):
        return execute(db, "UPDATE experiments SET snapshot=? WHERE id=?", parameters)

    @staticmethod
    def _accept_reports_select_device_reports_2(db, parameters=()):
        return execute(db, "SELECT max(sequence) FROM device_reports WHERE device_id=? AND assignment_id=?", parameters)

    @staticmethod
    def _accept_reports_select_assignments_2(db, parameters=()):
        return execute(db, "SELECT id FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", parameters)
