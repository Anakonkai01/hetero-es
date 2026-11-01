"""Shared product policy SQL."""

from .base import execute


class PoliciesRepository:
    @staticmethod
    def read_setting_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key=?", parameters)

    @staticmethod
    def set_disabled_workers_settings(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES (?,?)", parameters)

    @staticmethod
    def has_device_reservation_device_reservations(db, parameters=()):
        return execute(db, "SELECT 1 FROM device_reservations WHERE device_id=?", parameters)

    @staticmethod
    def has_device_reservation_physical_reservations(db, parameters=()):
        return execute(db, "SELECT 1 FROM physical_reservations WHERE resource_id=?", parameters)

    @staticmethod
    def has_device_reservation_model_probe_reservations(db, parameters=()):
        return execute(db, "SELECT 1 FROM model_probe_reservations WHERE device_id=? OR resource_id=?", parameters)
