"""Bootstrap admission persistence."""

from .base import execute


class BootstrapRepository:
    @staticmethod
    def server_initialize_8(db, parameters=()):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES (:p0,:p1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )
