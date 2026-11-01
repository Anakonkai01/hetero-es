"""Product audit persistence."""

from .base import execute


class AuditRepository:
    @staticmethod
    def record(db, parameters):
        return execute(db, "INSERT INTO audit(actor,action,target,created,workspace_id) VALUES (?,?,?,?,?)", parameters)
