"""Metadata backup status SQL."""

from .base import execute


class MetadataRepository:
    @staticmethod
    def set_backup_status(db, parameters):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES (?,?)", parameters)
