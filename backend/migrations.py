"""Versioned, transactional migration of the original single-lab database."""

import json

SCHEMA_VERSION = 1


def migrate(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError("Database belongs to a newer product version")
    if version == SCHEMA_VERSION:
        return
    # Do not rewrite experiment bodies, snapshots, sessions or FIFO sequence IDs.
    db.execute("BEGIN IMMEDIATE")
    db.execute(
        "CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL,creator TEXT NOT NULL)"
    )
    db.execute(
        'CREATE TABLE memberships(workspace_id TEXT NOT NULL,user_id TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ("ADMIN","PARTICIPANT")),PRIMARY KEY(workspace_id,user_id))'
    )
    db.execute(
        "CREATE TABLE invitations(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,user_id TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL)"
    )
    db.execute('CREATE UNIQUE INDEX pending_invitation ON invitations(workspace_id,user_id) WHERE status="PENDING"')
    db.execute("CREATE TABLE worker_assignments(worker_id TEXT PRIMARY KEY,owner TEXT NOT NULL,workspace_id TEXT)")
    db.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
    db.execute("ALTER TABLE audit ADD COLUMN workspace_id TEXT")
    db.execute('UPDATE audit SET workspace_id="lab"')
    profiles = [json.loads(row["profile"]) for row in db.execute("SELECT profile FROM users ORDER BY rowid")]
    # Legacy bootstrap migration only: subsequent authorization uses persisted
    # privileges and membership, never a special username.
    creator = next(
        (p["userId"] for p in profiles if p["username"] == "admin"), profiles[0]["userId"] if profiles else "bootstrap"
    )
    db.execute(
        "INSERT INTO workspaces VALUES (?,?,?,?)",
        ("lab", "HeteroES Lab", "Private GPU pool · FIFO · one active experiment", creator),
    )
    for p in profiles:
        p.update(
            accountStatus="ACTIVE", platformAdmin=p["userId"] == creator, canCreateWorkspace=p["userId"] == creator
        )
        db.execute("UPDATE users SET profile=? WHERE id=?", (json.dumps(p), p["userId"]))
        db.execute(
            "INSERT INTO memberships VALUES (?,?,?)",
            ("lab", p["userId"], "ADMIN" if p["userId"] == creator else "PARTICIPANT"),
        )
    db.execute("CREATE UNIQUE INDEX username ON users(json_extract(profile,'$.username'))")
    db.execute("INSERT INTO settings VALUES (?,?)", ("dispatchHold", "false"))
    db.execute("PRAGMA user_version=1")


def initialize_workspace_extras(db):
    """Tables added after schema version 1, created when missing: per-workspace settings and join requests."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS workspace_settings(workspace_id TEXT PRIMARY KEY,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS join_requests(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,user_id TEXT NOT NULL,
            status TEXT NOT NULL,created TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS pending_join_request ON join_requests(workspace_id,user_id)
            WHERE status="PENDING";
        """
    )


def initialize_agent_schema(store):
    with store.db() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("controlMode", "agent-v2"))
        db.executescript(
            "\n                CREATE TABLE IF NOT EXISTS pairing_codes (digest TEXT PRIMARY KEY,owner TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);\n                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY,worker_id TEXT UNIQUE NOT NULL,owner TEXT NOT NULL,name TEXT NOT NULL,token_digest TEXT NOT NULL,status TEXT NOT NULL,compute_url TEXT NOT NULL,self_test TEXT NOT NULL,boot_id TEXT,seen REAL NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 0,desired INTEGER NOT NULL DEFAULT 0,processes TEXT NOT NULL DEFAULT '[]');\n                CREATE TABLE IF NOT EXISTS assignments (id TEXT PRIMARY KEY,run_id TEXT UNIQUE NOT NULL,coordinator TEXT NOT NULL,epoch INTEGER NOT NULL,body TEXT NOT NULL,snapshot TEXT NOT NULL,released INTEGER NOT NULL DEFAULT 0);\n                CREATE TABLE IF NOT EXISTS device_reservations (device_id TEXT PRIMARY KEY,assignment_id TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS physical_reservations (resource_id TEXT PRIMARY KEY,assignment_id TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS device_commands (id TEXT PRIMARY KEY,device_id TEXT NOT NULL,dedupe TEXT NOT NULL UNIQUE,body TEXT NOT NULL,ack INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);\n                CREATE TABLE IF NOT EXISTS monitoring_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,assignment_id TEXT NOT NULL,body TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS device_telemetry_history(device_id TEXT NOT NULL,boot_id TEXT NOT NULL,sampled_at REAL NOT NULL,received_at REAL NOT NULL,body TEXT NOT NULL,PRIMARY KEY(device_id,boot_id,sampled_at));\n                CREATE TABLE IF NOT EXISTS device_reports (device_id TEXT NOT NULL,assignment_id TEXT NOT NULL,sequence INTEGER NOT NULL,PRIMARY KEY(device_id,assignment_id,sequence));\n            "
        )
        if "telemetry" not in {r[1] for r in db.execute("PRAGMA table_info(devices)")}:
            db.execute("ALTER TABLE devices ADD COLUMN telemetry TEXT")
        if "bulk_url" not in {r[1] for r in db.execute("PRAGMA table_info(devices)")}:
            db.execute("ALTER TABLE devices ADD COLUMN bulk_url TEXT")
        schema = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='assignments'").fetchone()[0]
        if "run_id TEXT UNIQUE" in schema:
            db.executescript(
                "\n                    BEGIN IMMEDIATE;\n                    ALTER TABLE assignments RENAME TO assignments_v2;\n                    CREATE TABLE assignments(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,coordinator TEXT NOT NULL,\n                        epoch INTEGER NOT NULL,body TEXT NOT NULL,snapshot TEXT NOT NULL,released INTEGER NOT NULL DEFAULT 0);\n                    INSERT INTO assignments SELECT * FROM assignments_v2;\n                    DROP TABLE assignments_v2;\n                    COMMIT;\n                "
            )
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS active_assignment_per_run ON assignments(run_id) WHERE released=0"
        )
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS assignment_epoch ON assignments(run_id,epoch)")
        for row in db.execute(
            "SELECT r.assignment_id,d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id"
        ).fetchall():
            resource = json.loads(row["self_test"]).get("gpuUUID")
            if resource:
                old = db.execute(
                    "SELECT assignment_id FROM physical_reservations WHERE resource_id=?", (resource,)
                ).fetchone()
                if old and old[0] != row["assignment_id"]:
                    raise RuntimeError("Conflicting physical GPU ownership; keep dispatch held")
                db.execute("INSERT OR IGNORE INTO physical_reservations VALUES (?,?)", (resource, row["assignment_id"]))


def initialize_product_schema(db):
    db.executescript(
        "\n                PRAGMA journal_mode=WAL;\n                CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, hash TEXT NOT NULL, profile TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);\n                CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, snapshot TEXT);\n                CREATE TABLE IF NOT EXISTS queue (sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL UNIQUE);\n                CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, target TEXT, created TEXT);\n            "
    )


def initialize_study_schema(db):
    db.executescript(
        "\n                CREATE TABLE IF NOT EXISTS study_assets(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,owner TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL);\n                CREATE TABLE IF NOT EXISTS study_uploads(id TEXT PRIMARY KEY,asset_id TEXT NOT NULL,name TEXT NOT NULL,object_sha TEXT NOT NULL,upload_key TEXT NOT NULL,size INTEGER NOT NULL);\n            "
    )


def initialize_templates_schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS experiment_templates (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, owner_id TEXT NOT NULL, name TEXT NOT NULL, config TEXT NOT NULL, created TEXT NOT NULL)"
    )


def initialize_notifications_schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, kind TEXT NOT NULL, params TEXT NOT NULL, target TEXT NOT NULL, created TEXT NOT NULL, read_at TEXT, dedupe TEXT NOT NULL UNIQUE)"
    )


def initialize_recovery_schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS cloud_downloads(digest TEXT PRIMARY KEY,user_id TEXT NOT NULL,session_digest TEXT NOT NULL,run_id TEXT NOT NULL,sha TEXT NOT NULL,expires REAL NOT NULL)"
    )


def initialize_recovery_downloads_schema(db):
    db.executescript(
        "CREATE TABLE IF NOT EXISTS cloud_objects(sha TEXT PRIMARY KEY,size INTEGER NOT NULL,status TEXT NOT NULL,upload_plan TEXT,expires REAL);\n                CREATE TABLE IF NOT EXISTS recovery_points(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,generation INTEGER NOT NULL,final INTEGER NOT NULL,status TEXT NOT NULL,manifest TEXT NOT NULL,error TEXT,created REAL NOT NULL);\n                CREATE TABLE IF NOT EXISTS cloud_refs(point_id TEXT NOT NULL,sha TEXT NOT NULL,PRIMARY KEY(point_id,sha));\n                CREATE TABLE IF NOT EXISTS cloud_requests(month TEXT PRIMARY KEY,class_a INTEGER NOT NULL,class_b INTEGER NOT NULL);"
    )
