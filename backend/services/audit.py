"""Audit policy; timestamps remain the original product clock."""

from ..core.clock import now
from ..repositories.audit import AuditRepository as repository


class AuditService:
    def audit(self, db, actor, action, target, workspace_id=None):
        repository.record(db, (actor, action, target, now(), workspace_id))
