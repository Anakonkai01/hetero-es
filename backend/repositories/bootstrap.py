"""Bootstrap admission persistence."""

from .base import execute


class BootstrapRepository:
    @staticmethod
    def server_initialize_8(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES (?,?)", parameters)
