"""Metadata backup status SQL."""

from .base import execute


class MetadataRepository:
    @staticmethod
    def set_backup_status(db, parameters):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES (:p0,:p1) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )
