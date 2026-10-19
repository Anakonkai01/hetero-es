"""In-app notifications: a projection of what happened, kept per person with a read state.

Nothing here is written by the code that does the work. Each look at the list first catches up with the audit log
(accounts, devices) and with experiments that ended, creating a row per fact (a unique key makes it happen once).
Rows hold a kind and parameters, never English text, so the interface can translate them.
"""

from .migrations import initialize_notifications_schema
from datetime import datetime, timezone
import json

from fastapi import Depends, HTTPException

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
            initialize_notifications_schema(db)
            db.execute("CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id, id)")
        self.start_following()

    def _add(self, db, user_id, kind, params, target, dedupe):
        db.execute(
            "INSERT OR IGNORE INTO notifications(user_id,kind,params,target,created,dedupe) VALUES (?,?,?,?,?,?)",
            (user_id, kind, json.dumps(params, sort_keys=True), target, _stamp(), dedupe),
        )

    def _administrators(self, db):
        return [
            row["id"]
            for row in db.execute("SELECT id, profile FROM users")
            if (lambda p: p.get("platformAdmin") and p.get("accountStatus") == "ACTIVE")(json.loads(row["profile"]))
        ]

    def start_following(self):
        """Fix the starting point the first time this lab runs with notifications, so history is never dug up; later starts keep it."""
        with self.store.db() as db:
            if db.execute("SELECT 1 FROM settings WHERE key='notificationCursor'").fetchone() is None:
                latest = db.execute("SELECT COALESCE(MAX(sequence),0) FROM audit").fetchone()[0]
                db.execute("INSERT OR REPLACE INTO settings VALUES ('notificationCursor',?)", (json.dumps(latest),))
                db.execute(
                    "INSERT OR REPLACE INTO settings VALUES ('notificationSince',?)",
                    (json.dumps(datetime.now(timezone.utc).timestamp()),),
                )

    def catch_up(self):
        """Create the notifications for everything that happened since the last look."""
        store = self.store
        with store.db() as db:
            cursor = db.execute("SELECT value FROM settings WHERE key='notificationCursor'").fetchone()
            horizon = db.execute("SELECT value FROM settings WHERE key='notificationSince'").fetchone()
            if cursor is None:
                return self.start_following()
            last = json.loads(cursor[0])
            since = json.loads(horizon[0]) if horizon else 0
            admins = self._administrators(db)
            newest = last
            for row in db.execute(
                "SELECT sequence, action, target FROM audit WHERE sequence>? ORDER BY sequence", (last,)
            ).fetchall():
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
                        db.execute("SELECT name, status FROM devices WHERE id=?", (row["target"],)).fetchone()
                        if db.execute("SELECT 1 FROM sqlite_master WHERE name='devices'").fetchone()
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
                db.execute("INSERT OR REPLACE INTO settings VALUES ('notificationCursor',?)", (json.dumps(newest),))
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
            rows = db.execute(
                "SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)
            ).fetchall()
            unread = db.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (user_id,)
            ).fetchone()[0]
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
                db.execute(
                    "UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL", (_stamp(), user_id)
                )
            else:
                numbers = [int(item) for item in ids if str(item).isdigit()]
                db.execute(
                    f"UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL AND id IN ({','.join('?' * len(numbers))})"
                    if numbers
                    else "SELECT 1",
                    (_stamp(), user_id, *numbers) if numbers else (),
                )


def install_notification_routes(app, store, user):
    notifications = Notifications(store)

    @app.get("/api/v1/notifications")
    def list_notifications(limit: int = 30, current=Depends(user)):
        if not 1 <= limit <= MAX_LIMIT:
            raise HTTPException(422, f"limit must be from 1 to {MAX_LIMIT}")
        notifications.catch_up()
        return notifications.listing(current["userId"], limit)

    @app.post("/api/v1/notifications/read")
    def read_notifications(body: dict, current=Depends(user)):
        ids, everything = body.get("ids"), body.get("all")
        if everything is True and ids is None:
            notifications.mark_read(current["userId"])
        elif isinstance(ids, list) and 1 <= len(ids) <= MAX_IDS and all(isinstance(item, (str, int)) for item in ids):
            notifications.mark_read(current["userId"], ids)
        else:
            raise HTTPException(422, f'Send {{"all": true}} or a list of 1 to {MAX_IDS} ids')
        return {"unread": notifications.listing(current["userId"], 1)["unread"]}
