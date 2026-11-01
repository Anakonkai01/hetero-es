"""Metadata snapshots use PostgreSQL17 tools and restore only to a fresh held database."""

import hashlib
import json
import os
from pathlib import Path
import uuid

import pytest
from sqlalchemy.engine import URL, make_url
from sqlalchemy import inspect, text

from backend.db.engine import Database
from backend.db.postgres_backup import PostgresBackupError, postgres_environment, restore_postgres, snapshot_postgres
from backend.services.devices import AgentRuntime
from backend.services.metadata_backup import create_metadata_backup
from backend.services.recovery_storage import RecoveryStorage
from backend.services.store import Store
from test_recovery_storage import Objects


def test_libpq_credentials_use_only_a_private_environment_and_ignore_ambient_services(monkeypatch):
    with monkeypatch.context() as ambient:
        ambient.setenv("PGSERVICE", "unrelated-service")
        ambient.setenv("PGHOST", "unrelated-host")
        target = URL.create(
            "postgresql+psycopg",
            username="fixture-user",
            password="fixture-private-password",
            host="127.0.0.1",
            port=15432,
            database="fixture",
        )
        environment = postgres_environment(target)
    if environment.get("PGPASSWORD") != target.password:
        pytest.fail("The database password was not passed through the private environment", pytrace=False)
    assert environment["PGHOST"] == "127.0.0.1" and environment["PGPORT"] == "15432"
    assert environment["PGDATABASE"] == "fixture" and environment["PGUSER"] == "fixture-user"
    assert "PGSERVICE" not in set(environment)
    assert environment["PGPASSFILE"] == os.devnull


if os.environ.get("HETEROES_TEST_DATABASE_URL") and os.environ.get("HETEROES_PG_DUMP"):

    @pytest.fixture
    def snapshot(tmp_path, fresh_postgres_database):
        source = Store(
            tmp_path / "source-state/product.sqlite",
            {"admin": "backup-fixture-password"},
            AgentRuntime(),
            database_url=fresh_postgres_database(),
        )
        try:
            with source.db() as db:
                db.execute(
                    "INSERT INTO device_reservations(device_id,assignment_id) VALUES (:p0,:p1)",
                    ("offline-device", "unknown-assignment"),
                )
                db.execute(
                    "INSERT INTO sessions(digest,user_id,expires) VALUES (:p0,:p1,:p2)",
                    ("fixture-session", "admin", 9999999999),
                )
            objects = Objects()
            storage = RecoveryStorage(source, objects, quota_bytes=10_000_000)
            result = create_metadata_backup(source, storage)
            assert result["status"] == "READY"
            root = Path(source.path).parent / "metadata-backups" / result["pointId"]
            manifest = json.loads((root / "manifest.json").read_text())
            assert manifest["databaseDriver"] == "postgresql" and manifest["dumpFormat"] == "custom"
            assert manifest["schemaName"] == "public" and manifest["pgDumpMajor"] == 17
            dump = root / "product.pgdump"
            assert hashlib.sha256(dump.read_bytes()).hexdigest() == manifest["sha256"]
            assert objects.data[manifest["objectKey"]] == dump.read_bytes()
            assert dump.stat().st_mode & 0o777 == 0o600
            assert not Path(source.path).exists()
            yield dump, manifest, source
        finally:
            source.close()

    def test_real_dump_restore_preserves_unknown_reservations_revokes_sessions_and_holds(
        snapshot, fresh_postgres_database
    ):
        dump, manifest, source = snapshot
        with Database(fresh_postgres_database()) as target:
            receipt = restore_postgres(dump, manifest, target)
            assert receipt["dispatchHeld"] and receipt["sessionsRevoked"] and receipt["reservationsPreserved"]
            with target.transaction() as db:
                assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
                assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
                assert [
                    tuple(row) for row in db.execute("SELECT device_id,assignment_id FROM device_reservations")
                ] == [("offline-device", "unknown-assignment")]
                assert db.execute("SELECT value FROM settings WHERE key=:p0", ("dispatchHold",)).fetchone()[0] == "true"

    def test_restore_refuses_existing_data_and_bad_checksum(snapshot, fresh_postgres_database):
        dump, manifest, source = snapshot
        with Database(fresh_postgres_database()) as populated:
            with populated.transaction() as db:
                db.execute("CREATE TABLE existing_payload(id BIGINT PRIMARY KEY)")
                db.execute("INSERT INTO existing_payload(id) VALUES (1)")
            with pytest.raises(ValueError, match="empty"):
                restore_postgres(dump, manifest, populated)
            with populated.transaction() as db:
                assert db.execute("SELECT id FROM existing_payload").fetchone()[0] == 1
        with Database(fresh_postgres_database()) as populated_schema:
            with populated_schema.transaction() as db:
                db.execute("CREATE SCHEMA pgx")
                db.execute("CREATE TABLE pgx.existing_payload(id BIGINT)")
            with pytest.raises(ValueError, match="empty"):
                restore_postgres(dump, manifest, populated_schema)
        with Database(fresh_postgres_database()) as invalid_schema:
            with pytest.raises(ValueError, match="Unsupported"):
                restore_postgres(dump, {**manifest, "schemaName": 'public"; SELECT 42; --'}, invalid_schema)
        dump.write_bytes(b"corrupt-fixture")
        with Database(fresh_postgres_database()) as empty:
            with pytest.raises(ValueError, match="checksum"):
                restore_postgres(dump, manifest, empty)


if os.environ.get("HETEROES_TEST_DATABASE_URL") and os.environ.get("HETEROES_PG_DUMP"):

    def test_restore_validation_failure_rolls_back_data_and_quarantine_together(snapshot, fresh_postgres_database):
        dump, manifest, source = snapshot
        with source.db() as db:
            db.execute("UPDATE settings SET value=:p0 WHERE key=:p1", ("invalid-agent-fixture", "controlMode"))
        storage = RecoveryStorage(source, Objects(), quota_bytes=10_000_000)
        point = create_metadata_backup(source, storage)
        root = Path(source.path).parent / "metadata-backups" / point["pointId"]
        invalid = json.loads((root / "manifest.json").read_text())
        with Database(fresh_postgres_database()) as target:
            with pytest.raises(PostgresBackupError):
                restore_postgres(root / "product.pgdump", invalid, target)
            assert inspect(target.engine).get_table_names() == []


def test_restore_command_has_a_help_entrypoint():
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "scripts/restore-postgres-metadata.py", "--help"], capture_output=True, text=True
    )
    assert completed.returncode == 0 and "--manifest" in completed.stdout


if os.environ.get("HETEROES_TEST_DATABASE_URL") and os.environ.get("HETEROES_PG_DUMP"):

    def test_restore_command_uses_an_environment_target_and_returns_only_safe_receipt(
        snapshot, fresh_postgres_database
    ):
        import subprocess
        import sys

        dump, manifest, source = snapshot
        target = fresh_postgres_database()
        environment = {**os.environ, "HETEROES_DATABASE_URL": target.render_as_string(hide_password=False)}
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/restore-postgres-metadata.py",
                "--database",
                str(dump),
                "--manifest",
                str(dump.with_name("manifest.json")),
            ],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0
        receipt = json.loads(completed.stdout)
        assert receipt["dispatchHeld"] and receipt["sessionsRevoked"] and receipt["reservationsPreserved"]
        if target.password in completed.stdout or target.password in completed.stderr:
            pytest.fail("The restore CLI exposed a connection secret", pytrace=False)


def test_backup_retention_deletes_the_manifest_payload_key_even_across_database_formats(lab):
    client, store, runtime, administrator = lab
    objects = Objects()
    root = Path(store.path).parent / "metadata-backups"
    root.mkdir(mode=0o700)
    historical = []
    for number in range(24):
        identifier = uuid.UUID(int=number + 1).hex
        point = root / identifier
        point.mkdir(mode=0o700)
        key = "metadata/" + identifier + "/product.pgdump"
        manifest_key = "metadata/" + identifier + "/manifest.json"
        (point / "manifest.json").write_text(json.dumps({"objectKey": key, "createdAt": number}))
        (point / "cloud-state.json").write_text('{"status":"READY"}')
        objects.put(key, b"historical-payload-fixture")
        objects.put(manifest_key, b"fixture")
        os.utime(point, (number, number))
        historical.append((point, key, manifest_key))
    result = create_metadata_backup(store, RecoveryStorage(store, objects, quota_bytes=20_000_000))
    assert result["status"] == "READY"
    oldest, payload, published_manifest = historical[0]
    assert not oldest.exists() and payload not in objects.data and published_manifest not in objects.data
    assert len(list(root.iterdir())) == 24
    assert all(point.exists() and key in objects.data for point, key, manifest_key in historical[1:])


def test_backup_rejects_an_incompatible_client_major_before_creating_a_snapshot(tmp_path, monkeypatch):
    from types import SimpleNamespace

    executable = tmp_path / "pg_dump"
    executable.write_text("#!/bin/sh\nprintf '%s\\n' 'pg_dump (PostgreSQL) 18.0'\n")
    executable.chmod(0o700)
    monkeypatch.setenv("HETEROES_PG_DUMP", str(executable))
    destination = tmp_path / "unexpected.pgdump"
    with pytest.raises(ValueError, match="PostgreSQL17"):
        snapshot_postgres(SimpleNamespace(dialect="postgresql"), destination)
    assert not destination.exists()


def test_failed_tool_stderr_does_not_escape_into_a_public_error(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from backend.db.postgres_backup import _run

    private = "fixture-tool-credential-that-must-not-be-logged"
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=private)
    )
    with pytest.raises(PostgresBackupError) as raised:
        _run(["fixture-pg-tool"])
    if private in str(raised.value):
        pytest.fail("The command error exposed private stderr", pytrace=False)
