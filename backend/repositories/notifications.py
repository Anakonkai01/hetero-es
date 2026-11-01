"""Notifications SQL; transaction ownership is separate."""

from ..db.dialect import bind_list
from .base import execute


class NotificationsRepository:
    @staticmethod
    def _add_insert_notifications(db, parameters=()):
        return execute(
            db,
            "INSERT INTO notifications(user_id,kind,params,target,created,dedupe) VALUES (:p0,:p1,:p2,:p3,:p4,:p5) ON CONFLICT DO NOTHING",
            parameters,
        )

    @staticmethod
    def _administrators_select_users(db, parameters=()):
        return execute(db, "SELECT id, profile FROM users", parameters)

    @staticmethod
    def start_following_insert_settings(db, parameters=()):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES ('notificationCursor',:p0) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )

    @staticmethod
    def start_following_insert_settings_2(db, parameters=()):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES ('notificationSince',:p0) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )

    @staticmethod
    def catch_up_insert_settings(db, parameters=()):
        return execute(
            db,
            "INSERT INTO settings(key,value)  VALUES ('notificationCursor',:p0) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            parameters,
        )

    @staticmethod
    def mark_read_update_notifications(db, parameters=()):
        return execute(db, "UPDATE notifications SET read_at=:p0 WHERE user_id=:p1 AND read_at IS NULL", parameters)

    @staticmethod
    def mark_read_update_notifications_2(db, parameters=(), *, numbers):
        return execute(
            db,
            f"UPDATE notifications SET read_at=:p0 WHERE user_id=:p1 AND read_at IS NULL AND id IN ({bind_list(numbers, start=2)})"
            if numbers
            else "SELECT 1",
            parameters,
        )

    @staticmethod
    def catch_up_select_settings(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key='notificationCursor'", parameters)

    @staticmethod
    def catch_up_select_settings_2(db, parameters=()):
        return execute(db, "SELECT value FROM settings WHERE key='notificationSince'", parameters)

    @staticmethod
    def catch_up_select_audit(db, parameters=()):
        return execute(
            db, "SELECT sequence, action, target FROM audit WHERE sequence>:p0 ORDER BY sequence", parameters
        )

    @staticmethod
    def listing_select_notifications(db, parameters=()):
        return execute(db, "SELECT * FROM notifications WHERE user_id=:p0 ORDER BY id DESC LIMIT :p1", parameters)

    @staticmethod
    def start_following_select_settings(db, parameters=()):
        return execute(db, "SELECT 1 FROM settings WHERE key='notificationCursor'", parameters)

    @staticmethod
    def listing_select_notifications_2(db, parameters=()):
        return execute(db, "SELECT COUNT(*) FROM notifications WHERE user_id=:p0 AND read_at IS NULL", parameters)

    @staticmethod
    def start_following_select_audit(db, parameters=()):
        return execute(db, "SELECT COALESCE(MAX(sequence),0) FROM audit", parameters)

    @staticmethod
    def catch_up_select_sqlite_master(db, parameters=()):
        return execute(
            db,
            "SELECT 1 FROM pg_tables WHERE schemaname=current_schema() AND tablename='devices'"
            if getattr(db, "dialect", "sqlite") == "postgresql"
            else "SELECT 1 FROM sqlite_master WHERE name='devices'",
            parameters,
        )

    @staticmethod
    def catch_up_select_devices(db, parameters=()):
        return execute(db, "SELECT name, status FROM devices WHERE id=:p0", parameters)
