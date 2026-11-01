"""The product schema and its durable constraints must agree on both real database dialects."""

import json
from pathlib import Path
import warnings

from argon2 import PasswordHasher
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, SAWarning

from backend.db.engine import Database

BASELINE = json.loads(
    (
        Path(__file__).parent / "fixtures/archive/docs/evidence/2026-11-01-backend-inventory/schema-before.json"
    ).read_text()
)
ORDERED = {
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
}


def _contract(owner):
    inspector = inspect(owner.engine)
    tables = {}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SAWarning, message="Skipped unsupported reflection.*")
        for table in inspector.get_table_names():
            if table == "entries":
                continue
            columns = inspector.get_columns(table)
            unique = {
                tuple(item["column_names"])
                for item in inspector.get_unique_constraints(table)
                if item["column_names"] and None not in item["column_names"]
            }
            unique.update(
                tuple(item["column_names"])
                for item in inspector.get_indexes(table)
                if item["unique"] and item["column_names"] and None not in item["column_names"]
            )
            tables[table] = {
                "columns": [(c["name"], c["type"]._type_affinity.__name__) for c in columns],
                "pk": inspector.get_pk_constraint(table)["constrained_columns"],
                "unique": sorted(unique),
            }
    return tables


def test_schema_preserves_old_columns_primary_keys_and_cross_dialect_uniqueness(database, tmp_path):
    owner, _ = database
    owner.initialize({}, PasswordHasher())
    with Database(tmp_path / "comparison.sqlite") as sqlite:
        sqlite.initialize({}, PasswordHasher())
        assert _contract(owner) == _contract(sqlite)
    contract = _contract(owner)
    assert set(contract) == set(BASELINE["tables"]) | {"schema_versions"}
    for table, legacy in BASELINE["tables"].items():
        expected = [c["name"] for c in legacy["columns"]]
        if table in ORDERED:
            expected.append("_insert_order")
        assert [name for name, _ in contract[table]["columns"]] == expected
        assert contract[table]["pk"] == [c["name"] for c in sorted(legacy["columns"], key=lambda c: c["pk"]) if c["pk"]]


def test_bootstrap_is_persistent_and_username_partial_indexes_remain_enforced(database):
    owner, another_owner = database
    hasher = PasswordHasher()
    owner.initialize({"admin": "fixture-bootstrap-password"}, hasher)
    with owner.transaction() as connection:
        profile = json.loads(connection.execute("SELECT profile FROM users WHERE id=:p0", ("admin",)).fetchone()[0])
        assert profile["accountStatus"] == "ACTIVE" and profile["platformAdmin"] is True
        with pytest.raises(IntegrityError):
            connection.execute(
                "INSERT INTO users(id,hash,profile) VALUES (:p0,:p1,:p2)", ("other", "fixture", json.dumps(profile))
            )
        for number in (1, 2):
            connection.execute(
                "INSERT INTO invitations(id,workspace_id,user_id,status,created) VALUES (:p0,:p1,:p2,:p3,:p4)",
                (str(number), "lab", "admin", "ACCEPTED", "fixture"),
            )
        connection.execute(
            "INSERT INTO invitations(id,workspace_id,user_id,status,created) VALUES (:p0,:p1,:p2,:p3,:p4)",
            ("3", "lab", "admin", "PENDING", "fixture"),
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                "INSERT INTO invitations(id,workspace_id,user_id,status,created) VALUES (:p0,:p1,:p2,:p3,:p4)",
                ("4", "lab", "admin", "PENDING", "fixture"),
            )
        connection.execute("DELETE FROM users WHERE id=:p0", ("admin",))
    other = another_owner()
    try:
        other.initialize({"admin": "fixture-bootstrap-password"}, hasher)
        with other.transaction(write=False) as connection:
            assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
            assert connection.execute("SELECT version FROM schema_versions").fetchone()[0] == 1
    finally:
        other.close()


def test_internal_order_is_monotonic_and_integer_fields_keep_64_bits(database):
    owner, _ = database
    owner.initialize({}, PasswordHasher())
    with owner.transaction() as connection:
        for identifier in ("z-first", "a-second"):
            connection.execute(
                "INSERT INTO study_uploads(id,asset_id,name,object_sha,upload_key,size) VALUES (:p0,:p1,:p2,:p3,:p4,:p5)",
                (identifier, "asset", "fixture", "sha", "key", 2**34),
            )
        rows = connection.execute("SELECT id,size,_insert_order FROM study_uploads ORDER BY _insert_order").fetchall()
        assert [r["id"] for r in rows] == ["z-first", "a-second"]
        assert rows[0]["_insert_order"] < rows[1]["_insert_order"]
        assert [r["size"] for r in rows] == [2**34, 2**34]
        sampled, received = 1712345678.1234567, 1712345678.1244566
        connection.execute(
            "INSERT INTO device_telemetry_history(device_id,boot_id,sampled_at,received_at,body) "
            "VALUES (:p0,:p1,:p2,:p3,:p4)",
            ("device", "boot", sampled, received, "{}"),
        )
        assert tuple(connection.execute("SELECT sampled_at,received_at FROM device_telemetry_history").fetchone()) == (
            sampled,
            received,
        )


@pytest.mark.sqlite_file(
    reason="additive migration preserves existing SQLite insertion order and exact experiment bytes"
)
def test_existing_version_one_rows_keep_their_order_and_experiment_bytes(tmp_path):
    import sqlite3
    import threading

    from backend.db.database import SQLiteDatabase

    path = tmp_path / "version-one.sqlite"
    legacy = SQLiteDatabase(path, threading.RLock())
    legacy.initialize(
        {"z-first": "fixture-bootstrap-password", "a-second": "fixture-bootstrap-password"}, PasswordHasher()
    )
    with legacy.connection() as db:
        for identifier in ("z-first", "a-second"):
            db.execute(
                "INSERT INTO experiments VALUES (?,?,?,?)",
                (identifier, identifier, '{ "fixture": 1 }', '{ "unchanged": true }'),
            )
        profiles = [tuple(row) for row in db.execute("SELECT id,profile FROM users ORDER BY rowid")]
    with Database(path) as owner:
        owner.initialize({}, PasswordHasher())
        with owner.transaction() as db:
            assert [tuple(row) for row in db.execute("SELECT id,profile FROM users ORDER BY _insert_order")] == profiles
            orders = [row[0] for row in db.execute("SELECT _insert_order FROM users ORDER BY _insert_order")]
            assert 0 < orders[0] < orders[1]
            assert [
                tuple(row) for row in db.execute("SELECT id,body,snapshot FROM experiments ORDER BY _insert_order")
            ] == [(identifier, '{ "fixture": 1 }', '{ "unchanged": true }') for identifier in ("z-first", "a-second")]
            previous = db.execute("SELECT max(_insert_order) FROM experiments").fetchone()[0]
            db.execute("INSERT INTO experiments(id,owner,body) VALUES (:p0,:p1,:p2)", ("newest", "owner", "{}"))
            assert (
                db.execute("SELECT _insert_order FROM experiments WHERE id=:p0", ("newest",)).fetchone()[0] > previous
            )
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
