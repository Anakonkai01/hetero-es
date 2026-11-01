"""Notification projection schema initialization, owned by the database layer."""

from .migrations import initialize_notifications_schema


def initialize_notification_projection(db):
    initialize_notifications_schema(db)
    db.execute("CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id, id)")
