"""Notifications SQL; transaction ownership is separate."""

from .base import execute


class NotificationsRepository:
    @staticmethod
    def _add_insert_notifications(db, parameters=()):
        return execute(
            db,
            "INSERT OR IGNORE INTO notifications(user_id,kind,params,target,created,dedupe) VALUES (?,?,?,?,?,?)",
            parameters,
        )

    @staticmethod
    def _administrators_select_users(db, parameters=()):
        return execute(db, "SELECT id, profile FROM users", parameters)

    @staticmethod
    def start_following_insert_settings(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES ('notificationCursor',?)", parameters)

    @staticmethod
    def start_following_insert_settings_2(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES ('notificationSince',?)", parameters)

    @staticmethod
    def catch_up_insert_settings(db, parameters=()):
        return execute(db, "INSERT OR REPLACE INTO settings VALUES ('notificationCursor',?)", parameters)

    @staticmethod
    def mark_read_update_notifications(db, parameters=()):
        return execute(db, "UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", parameters)

    @staticmethod
    def mark_read_update_notifications_2(db, parameters=(), *, numbers):
        return execute(
            db,
            f"UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND id IN ({','.join('?' * len(numbers))})"
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
        return execute(db, "SELECT sequence, action, target FROM audit WHERE sequence>? ORDER BY sequence", parameters)

    @staticmethod
    def listing_select_notifications(db, parameters=()):
        return execute(db, "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?", parameters)

    @staticmethod
    def start_following_select_settings(db, parameters=()):
        return execute(db, "SELECT 1 FROM settings WHERE key='notificationCursor'", parameters)

    @staticmethod
    def listing_select_notifications_2(db, parameters=()):
        return execute(db, "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", parameters)

    @staticmethod
    def start_following_select_audit(db, parameters=()):
        return execute(db, "SELECT COALESCE(MAX(sequence),0) FROM audit", parameters)

    @staticmethod
    def catch_up_select_sqlite_master(db, parameters=()):
        return execute(db, "SELECT 1 FROM sqlite_master WHERE name='devices'", parameters)

    @staticmethod
    def catch_up_select_devices(db, parameters=()):
        return execute(db, "SELECT name, status FROM devices WHERE id=?", parameters)
