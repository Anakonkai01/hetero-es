"""Shared cluster identity and scheduler diagnostic SQL."""

from .base import execute


class ClusterStateRepository:
    @staticmethod
    def read(db, key):
        return execute(db, "SELECT value FROM settings WHERE key=:p0", (key,)).fetchone()

    @staticmethod
    def write(db, key, value):
        execute(
            db,
            "INSERT INTO settings(key,value) VALUES (:p0,:p1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
