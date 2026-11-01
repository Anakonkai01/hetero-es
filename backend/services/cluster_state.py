"""Durable cloud state shared by API replicas; desktop retains process-local diagnostics/configured identity."""

import json
import re
import uuid

from ..repositories.cluster_state import ClusterStateRepository as repository

_IDENTITY = re.compile(r"[a-f0-9]{32}\Z")
_ERROR_TYPE = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,127}\Z")


def _error_type(value):
    return value is None or isinstance(value, str) and _ERROR_TYPE.fullmatch(value) is not None


class ClusterStateService:
    def __init__(self, store):
        self.store, self._local_error = store, None

    @property
    def shared(self):
        return self.store.database.dialect == "postgresql"

    def identity(self, configured):
        if not self.shared:
            return configured
        if configured is not None and (not isinstance(configured, str) or not _IDENTITY.fullmatch(configured)):
            raise ValueError("Invalid configured cluster identity")
        with self.store.db() as db:
            row = repository.read(db, "clusterId")
            if row:
                identifier = json.loads(row[0])
                if not isinstance(identifier, str) or not _IDENTITY.fullmatch(identifier):
                    raise RuntimeError("Invalid shared cluster identity")
                if configured is not None and configured != identifier:
                    raise ValueError("Configured identity conflicts with the shared cluster identity")
                return identifier
            identifier = configured or uuid.uuid4().hex
            repository.write(db, "clusterId", json.dumps(identifier))
            return identifier

    @property
    def last_error(self):
        if not self.shared:
            return self._local_error
        with self.store.db() as db:
            row = repository.read(db, "schedulerLastError")
        try:
            value = json.loads(row[0]) if row else None
        except (TypeError, ValueError):
            return "InvalidSchedulerDiagnostic"
        return value if _error_type(value) else "InvalidSchedulerDiagnostic"

    @last_error.setter
    def last_error(self, value):
        if not _error_type(value):
            raise ValueError("Scheduler diagnostics must be an error type")
        if not self.shared:
            self._local_error = value
            return
        with self.store.db() as db:
            repository.write(db, "schedulerLastError", json.dumps(value))
