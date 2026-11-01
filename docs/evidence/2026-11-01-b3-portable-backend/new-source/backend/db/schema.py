"""Schema ownership: existing SQLite migrations, explicit PostgreSQL DDL, additive ordering/version metadata."""

from contextlib import nullcontext
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from .database import SQLiteDatabase
from . import migrations

ORDERED_TABLES = (
    "users",
    "devices",
    "assignments",
    "assignment_members",
    "study_assets",
    "study_uploads",
    "workspaces",
    "join_requests",
    "experiments",
    "model_probe_jobs",
)


def initialize_database(owner, passwords, hasher):
    with owner.lock:
        if owner.dialect == "sqlite":
            _initialize_sqlite(owner, passwords, hasher)
        else:
            _initialize_postgres(owner, passwords, hasher)
        owner.schema_ready = True


def _initialize_sqlite(owner, passwords, hasher):
    # executescript has legacy commit semantics. Run old migrations on a dedicated sqlite3 connection,
    # before SQLAlchemy starts owning ordinary business transactions; never undo a borrowed transaction.
    legacy = SQLiteDatabase(owner.url.database, owner.lock)
    legacy.initialize(passwords, hasher)
    with legacy.connection() as db:
        previous = db.execute("SELECT value FROM settings WHERE key='controlMode'").fetchone()
        migrations.initialize_agent_schema(SimpleNamespace(db=lambda: nullcontext(db)))
        for initializer in (
            migrations.initialize_study_schema,
            migrations.initialize_templates_schema,
            migrations.initialize_notifications_schema,
            migrations.initialize_recovery_schema,
            migrations.initialize_recovery_downloads_schema,
        ):
            initializer(db)
        if previous is None:
            db.execute("DELETE FROM settings WHERE key='controlMode'")
        else:
            db.execute("UPDATE settings SET value=? WHERE key='controlMode'", (previous[0],))
        db.execute("CREATE INDEX IF NOT EXISTS notifications_user ON notifications(user_id,id)")
        for table in ORDERED_TABLES:
            columns = {row[1] for row in db.execute("PRAGMA table_info(" + table + ")")}
            if "_insert_order" not in columns:
                db.execute("ALTER TABLE " + table + " ADD COLUMN _insert_order INTEGER NOT NULL DEFAULT 0")
                db.execute("UPDATE " + table + " SET _insert_order=rowid")
            # rowid is confined to the legacy SQLite migration adapter, never queried by repositories.
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS order_"
                + table
                + " AFTER INSERT ON "
                + table
                + " WHEN NEW._insert_order=0 BEGIN UPDATE "
                + table
                + " SET _insert_order=NEW.rowid WHERE rowid=NEW.rowid; END"
            )
        db.execute("CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY,applied TEXT NOT NULL)")
        db.execute(
            "INSERT INTO schema_versions(version,applied) VALUES (?,?) ON CONFLICT(version) DO NOTHING",
            (1, datetime.now(timezone.utc).isoformat()),
        )


def _initialize_postgres(owner, passwords, hasher):
    with owner.transaction() as db:
        ddl = Path(__file__).with_name("postgres_schema.sql").read_text()
        for statement in ddl.split(";"):
            if statement.strip():
                db.execute(statement)
        version = db.execute("SELECT version FROM schema_versions ORDER BY version DESC LIMIT 1").fetchone()
        if version:
            if version[0] != 1:
                raise RuntimeError("Database belongs to an unsupported product version")
            return
        profiles = []
        for name, password in passwords.items():
            profile = {"userId": name, "username": name, "displayName": name.title(), "canCreateWorkspace": False}
            profiles.append(profile)
            db.execute(
                "INSERT INTO users(id,hash,profile) VALUES (:p0,:p1,:p2) ON CONFLICT DO NOTHING",
                (name, hasher.hash(password), json.dumps(profile)),
            )
        creator = next(
            (p["userId"] for p in profiles if p["username"] == "admin"),
            profiles[0]["userId"] if profiles else "bootstrap",
        )
        db.execute(
            "INSERT INTO workspaces(id,name,description,creator) VALUES (:p0,:p1,:p2,:p3)",
            ("lab", "HeteroES Lab", "Private GPU pool · FIFO · one active experiment", creator),
        )
        for profile in profiles:
            identifier = profile["userId"]
            profile.update(
                accountStatus="ACTIVE", platformAdmin=identifier == creator, canCreateWorkspace=identifier == creator
            )
            db.execute("UPDATE users SET profile=:p0 WHERE id=:p1", (json.dumps(profile), identifier))
            db.execute(
                "INSERT INTO memberships(workspace_id,user_id,role) VALUES (:p0,:p1,:p2)",
                ("lab", identifier, "ADMIN" if identifier == creator else "PARTICIPANT"),
            )
        db.execute("INSERT INTO settings(key,value) VALUES (:p0,:p1)", ("dispatchHold", "false"))
        db.execute(
            "INSERT INTO schema_versions(version,applied) VALUES (:p0,:p1)",
            (1, datetime.now(timezone.utc).isoformat()),
        )
