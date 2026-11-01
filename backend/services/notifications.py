"""Notifications business operations; HTTP responses stay in api/."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from ..core.errors import ServiceError
from ..repositories.notifications import NotificationsRepository as repository
from ..db.projections import initialize_notification_projection

MAX_LIMIT = 100

MAX_IDS = 200

RUN_KINDS = {"COMPLETED": "run.completed", "FAILED": "run.failed", "CANCELLED": "run.cancelled"}

ACCOUNT_KINDS = {"ACTIVE": "account.approved", "REJECTED": "account.rejected", "SUSPENDED": "account.suspended"}


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _epoch(iso):
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return None


class Notifications:
    def __init__(self, store):
        self.store = store
        with store.db() as db:
            initialize_notification_projection(db)
        self.start_following()

    def _add(self, db, user_id, kind, params, target, dedupe):
        repository._add_insert_notifications(
            db, (user_id, kind, json.dumps(params, sort_keys=True), target, _stamp(), dedupe)
        )

    def _administrators(self, db):
        return [
            row["id"]
            for row in repository._administrators_select_users(db, ())
            if (lambda p: p.get("platformAdmin") and p.get("accountStatus") == "ACTIVE")(json.loads(row["profile"]))
        ]

    def start_following(self):
        """Fix the starting point the first time this lab runs with notifications, so history is never dug up; later starts keep it."""
        with self.store.db() as db:
            if repository.start_following_select_settings(db, ()).fetchone() is None:
                latest = repository.start_following_select_audit(db, ()).fetchone()[0]
                repository.start_following_insert_settings(db, (json.dumps(latest),))
                repository.start_following_insert_settings_2(db, (json.dumps(datetime.now(timezone.utc).timestamp()),))

    def catch_up(self):
        """Create the notifications for everything that happened since the last look."""
        store = self.store
        with store.db() as db:
            cursor = repository.catch_up_select_settings(db, ()).fetchone()
            horizon = repository.catch_up_select_settings_2(db, ()).fetchone()
            if cursor is None:
                return self.start_following()
            last = json.loads(cursor[0])
            since = json.loads(horizon[0]) if horizon else 0
            admins = self._administrators(db)
            newest = last
            for row in repository.catch_up_select_audit(db, (last,)).fetchall():
                newest = row["sequence"]
                if row["action"] == "REGISTER":
                    profile = store.profile(row["target"]) or {}
                    for admin in admins:
                        self._add(
                            db,
                            admin,
                            "account.request",
                            {"username": profile.get("username", ""), "displayName": profile.get("displayName", "")},
                            "/operations",
                            f"register:{row['target']}:{admin}",
                        )
                elif row["action"] == "ACCOUNT_UPDATE":
                    profile = store.profile(row["target"]) or {}
                    kind = ACCOUNT_KINDS.get(profile.get("accountStatus"))
                    if kind:
                        self._add(db, row["target"], kind, {}, "/get-started", f"account:{row['sequence']}")
                elif row["action"] == "DEVICE_ENROLLED":
                    device = (
                        repository.catch_up_select_devices(db, (row["target"],)).fetchone()
                        if repository.catch_up_select_sqlite_master(db, ()).fetchone()
                        else None
                    )
                    if device and device["status"] == "PENDING":
                        for admin in admins:
                            self._add(
                                db,
                                admin,
                                "device.request",
                                {"name": device["name"]},
                                "/operations",
                                f"device:{row['target']}:{admin}",
                            )
            if newest != last:
                repository.catch_up_insert_settings(db, (json.dumps(newest),))
        for body in store.list():
            kind = RUN_KINDS.get(body.get("status"))
            ended = _epoch(body.get("completedAt"))
            if kind and ended is not None and ended >= since and body.get("ownerUserId") and not body.get("archivedAt"):
                with store.db() as db:
                    self._add(
                        db,
                        body["ownerUserId"],
                        kind,
                        {"name": body.get("name", "")},
                        f"/experiments/{body['experimentId']}",
                        f"run:{body['experimentId']}:{body['status']}",
                    )

    def listing(self, user_id, limit):
        with self.store.db() as db:
            rows = repository.listing_select_notifications(db, (user_id, limit)).fetchall()
            unread = repository.listing_select_notifications_2(db, (user_id,)).fetchone()[0]
        return {
            "items": [
                {
                    "id": str(row["id"]),
                    "kind": row["kind"],
                    "params": json.loads(row["params"]),
                    "target": row["target"],
                    "created": row["created"],
                    "read": row["read_at"] is not None,
                }
                for row in rows
            ],
            "unread": unread,
        }

    def mark_read(self, user_id, ids=None):
        with self.store.db() as db:
            if ids is None:
                repository.mark_read_update_notifications(db, (_stamp(), user_id))
            else:
                numbers = [int(item) for item in ids if str(item).isdigit()]
                repository.mark_read_update_notifications_2(
                    db, (_stamp(), user_id, *numbers) if numbers else (), numbers=numbers
                )


def operations(store, user):
    notifications = Notifications(store)

    def list_notifications(limit: int = 30, *, current):
        if not 1 <= limit <= MAX_LIMIT:
            raise ServiceError(422, f"limit must be from 1 to {MAX_LIMIT}")
        notifications.catch_up()
        return notifications.listing(current["userId"], limit)

    def read_notifications(body: dict, *, current):
        ids, everything = body.get("ids"), body.get("all")
        if everything is True and ids is None:
            notifications.mark_read(current["userId"])
        elif isinstance(ids, list) and 1 <= len(ids) <= MAX_IDS and all(isinstance(item, (str, int)) for item in ids):
            notifications.mark_read(current["userId"], ids)
        else:
            raise ServiceError(422, f'Send {{"all": true}} or a list of 1 to {MAX_IDS} ids')
        return {"unread": notifications.listing(current["userId"], 1)["unread"]}

    return SimpleNamespace(list_notifications=list_notifications, read_notifications=read_notifications)
