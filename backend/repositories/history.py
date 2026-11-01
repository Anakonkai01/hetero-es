"""History SQL; transaction ownership is separate."""

from ..db.dialect import bind_list, json_text
from .base import execute


class HistoryRepository:
    @staticmethod
    def event_list_select_monitoring_events(db, parameters=(), *, runs):
        return execute(
            db,
            f"SELECT a.run_id,m.sequence,m.body FROM monitoring_events m JOIN assignments a ON a.id=m.assignment_id WHERE a.run_id IN ({bind_list(runs)}) AND {json_text(db, 'm.body', 'event')} IN (:p{len(runs)},:p{len(runs) + 1}) ORDER BY m.sequence",
            parameters,
        )

    @staticmethod
    def event_list_select_experiments(db, parameters=(), *, runs):
        return execute(db, f"SELECT id,snapshot FROM experiments WHERE id IN ({bind_list(runs)})", parameters)

    @staticmethod
    def audit_select_audit(db, parameters=()):
        return execute(db, "SELECT * FROM audit WHERE workspace_id=:p0 ORDER BY sequence DESC LIMIT 100", parameters)
