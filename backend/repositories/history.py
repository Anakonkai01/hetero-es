"""History SQL; transaction ownership is separate."""

from .base import execute


class HistoryRepository:
    @staticmethod
    def event_list_select_monitoring_events(db, parameters=(), *, runs):
        return execute(
            db,
            f"SELECT a.run_id,m.sequence,m.body FROM monitoring_events m JOIN assignments a ON a.id=m.assignment_id WHERE a.run_id IN ({','.join('?' * len(runs))}) AND json_extract(m.body,'$.event') IN (?,?) ORDER BY m.sequence",
            parameters,
        )

    @staticmethod
    def event_list_select_experiments(db, parameters=(), *, runs):
        return execute(db, f"SELECT id,snapshot FROM experiments WHERE id IN ({','.join('?' * len(runs))})", parameters)

    @staticmethod
    def audit_select_audit(db, parameters=()):
        return execute(db, "SELECT * FROM audit WHERE workspace_id=? ORDER BY sequence DESC LIMIT 100", parameters)
