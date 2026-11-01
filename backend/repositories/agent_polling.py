"""AgentPolling SQL; business decisions stay in the service mixin."""

from ..db.dialect import json_text
from .base import execute


class AgentPollingRepository:
    @staticmethod
    def poll_insert_settings(db, parameters=()):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES (:p0,:p1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )

    @staticmethod
    def poll_select_devices(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def poll_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT id,run_id,coordinator,epoch,body,snapshot,released FROM assignments WHERE released=0",
            parameters,
        )

    @staticmethod
    def poll_select_devices_2(db, parameters=()):
        return execute(
            db,
            "SELECT id,worker_id,owner,name,token_digest,status,compute_url,self_test,boot_id,seen,enabled,desired,processes,telemetry,bulk_url,keep_on FROM devices WHERE id=:p0",
            parameters,
        )

    @staticmethod
    def poll_select_assignments_2(db, parameters=()):
        return execute(
            db, "SELECT id,run_id,coordinator,epoch,body,snapshot,released FROM assignments WHERE id=:p0", parameters
        )

    @staticmethod
    def poll_select_assignments_3(db, parameters=()):
        return execute(db, "SELECT id,body FROM assignments WHERE released=1", parameters)

    @staticmethod
    def poll_select_assignments_4(db, parameters=()):
        return execute(db, "SELECT 1 FROM assignments WHERE id=:p0", parameters)

    @staticmethod
    def poll_select_device_reservations(db, parameters=()):
        return execute(db, "SELECT 1 FROM device_reservations WHERE device_id=:p0 AND assignment_id=:p1", parameters)

    @staticmethod
    def _refresh_observation_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET self_test=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def _refresh_observation_update_devices_2(db, parameters=()):
        return execute(db, "UPDATE devices SET telemetry=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def _refresh_observation_insert_device_telemetry_history(db, parameters=()):
        return execute(
            db,
            "INSERT INTO device_telemetry_history(device_id,boot_id,sampled_at,received_at,body)  VALUES (:p0,:p1,:p2,:p3,:p4) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def _refresh_observation_delete_device_telemetry_history(db, parameters=()):
        return execute(
            db,
            "DELETE FROM device_telemetry_history WHERE device_id=:p0 AND (device_id,boot_id,sampled_at) NOT IN (SELECT device_id,boot_id,sampled_at FROM device_telemetry_history WHERE device_id=:p1 ORDER BY received_at DESC LIMIT 180)",
            parameters,
        )

    @staticmethod
    def _refresh_observation_update_devices_3(db, parameters=()):
        return execute(db, "UPDATE devices SET telemetry=NULL WHERE id=:p0", parameters)

    @staticmethod
    def _update_boot_update_devices(db, parameters=()):
        return execute(
            db, "UPDATE devices SET boot_id=:p0,seen=:p1,enabled=:p2,desired=:p3,processes=:p4 WHERE id=:p5", parameters
        )

    @staticmethod
    def _update_boot_update_device_commands(db, parameters=()):
        return execute(
            db,
            f"UPDATE device_commands SET ack=1 WHERE device_id=:p0 AND {json_text(db, 'body', 'kind')}='SET_CONTRIBUTION'",
            parameters,
        )

    @staticmethod
    def _update_boot_update_device_commands_2(db, parameters=()):
        return execute(db, "UPDATE device_commands SET ack=1 WHERE id=:p0 AND device_id=:p1", parameters)

    @staticmethod
    def _update_boot_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.id,a.run_id,a.coordinator,a.epoch,a.body,a.snapshot,a.released FROM assignments a JOIN device_reservations r ON r.assignment_id=a.id WHERE r.device_id=:p0",
            parameters,
        )

    @staticmethod
    def _quarantine_processes_update_devices(db, parameters=()):
        return execute(db, "UPDATE devices SET status=:p0,enabled=0,desired=0 WHERE id=:p1", parameters)

    @staticmethod
    def _quarantine_processes_select_assignments(db, parameters=()):
        return execute(
            db,
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=:p0",
            parameters,
        )

    @staticmethod
    def _accept_events_select_assignments(db, parameters=()):
        return execute(db, "SELECT coordinator,epoch FROM assignments WHERE id=:p0", parameters)

    @staticmethod
    def _accept_events_insert_monitoring_events(db, parameters=()):
        return execute(
            db,
            "INSERT INTO monitoring_events(event_id,assignment_id,body) VALUES (:p0,:p1,:p2) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def _accept_events_select_assignments_2(db, parameters=()):
        return execute(db, "SELECT body,released FROM assignments WHERE id=:p0", parameters)

    @staticmethod
    def _accept_events_update_devices(db, parameters=()):
        return execute(
            db,
            "UPDATE devices SET status='QUARANTINED',enabled=0,desired=0 WHERE id=:p0 AND status='APPROVED'",
            parameters,
        )

    @staticmethod
    def _accept_reports_insert_device_reports(db, parameters=()):
        return execute(
            db, "INSERT INTO device_reports(device_id,assignment_id,sequence)  VALUES (:p0,:p1,:p2)", parameters
        )

    @staticmethod
    def _accept_reports_update_assignments(db, parameters=()):
        return execute(db, "UPDATE assignments SET snapshot=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def _accept_reports_select_assignments(db, parameters=()):
        return execute(
            db, "SELECT id,run_id,coordinator,epoch,body,snapshot,released FROM assignments WHERE id=:p0", parameters
        )

    @staticmethod
    def _accept_reports_select_device_reports(db, parameters=()):
        return execute(
            db, "SELECT 1 FROM device_reports WHERE device_id=:p0 AND assignment_id=:p1 AND sequence=:p2", parameters
        )

    @staticmethod
    def _accept_reports_update_experiments(db, parameters=()):
        return execute(db, "UPDATE experiments SET snapshot=:p0 WHERE id=:p1", parameters)

    @staticmethod
    def _accept_reports_select_device_reports_2(db, parameters=()):
        return execute(
            db, "SELECT max(sequence) FROM device_reports WHERE device_id=:p0 AND assignment_id=:p1", parameters
        )

    @staticmethod
    def _accept_reports_select_assignments_2(db, parameters=()):
        return execute(db, "SELECT id FROM assignments WHERE run_id=:p0 ORDER BY epoch DESC LIMIT 1", parameters)
