"""PostgreSQL17 metadata snapshots and atomic, held restores into an empty database."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from sqlalchemy import text

from .engine import LAB_WRITE_LOCK

_SCHEMA = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,62}\Z")


class PostgresBackupError(RuntimeError):
    pass


def postgres_environment(url):
    if url.get_backend_name() not in {"postgres", "postgresql"} or not url.host or not url.database or not url.username:
        raise ValueError("An explicit PostgreSQL host/database/user is required")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    environment.update(
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGDATABASE=url.database,
        PGUSER=url.username,
        PGPASSWORD=url.password or "",
        PGPASSFILE=os.devnull,
        PGSERVICEFILE=os.devnull,
        PGCONNECT_TIMEOUT="5",
        PGCLIENTENCODING="UTF8",
        PGAPPNAME="heteroes-metadata",
    )
    for key in ("options", "sslmode", "sslrootcert", "sslcert", "sslkey", "target_session_attrs"):
        if key in url.query:
            environment["PG" + key.replace("_", "").upper()] = url.query[key]
    return environment


def _run(arguments, environment=None):
    try:
        completed = subprocess.run(arguments, env=environment, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        raise PostgresBackupError("PostgreSQL metadata tool could not complete") from None
    if completed.returncode:
        # Tool stderr can contain restored data or connection details. Never publish it in HTTP/central logs.
        raise PostgresBackupError("PostgreSQL metadata tool failed")
    return completed.stdout.strip()


def _tool(variable, default):
    executable = os.environ.get(variable, default)
    version = _run([executable, "--version"])
    if not re.search(r"\(PostgreSQL\)\s+17(?:\.|$)", version):
        raise ValueError("PostgreSQL17 client tools are required")
    return executable, version


def snapshot_postgres(database, destination):
    if database.dialect != "postgresql":
        raise ValueError("PostgreSQL metadata snapshot requires PostgreSQL")
    executable, version = _tool("HETEROES_PG_DUMP", "pg_dump")
    with database.transaction(write=False) as db:
        schema = db.execute("SELECT current_schema()").fetchone()[0]
        server = int(db.execute("SELECT current_setting('server_version_num')").fetchone()[0])
    if not isinstance(schema, str) or not _SCHEMA.fullmatch(schema) or not 170000 <= server < 180000:
        raise ValueError("A PostgreSQL17 application schema is required")
    destination = Path(destination)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        _run(
            [
                executable,
                "--no-password",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--strict-names",
                '--schema="' + schema + '"',
                "--file=" + str(destination),
            ],
            postgres_environment(database.url),
        )
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {
        "databaseDriver": "postgresql",
        "dumpFormat": "custom",
        "schemaName": schema,
        "pgDumpMajor": 17,
        "pgDumpVersion": version,
    }


def _empty(database):
    with database.transaction(write=False) as db:
        return (
            db.execute("""
            SELECT count(*) FROM (
                SELECT relnamespace AS namespace FROM pg_class WHERE relkind IN ('r','p','S','v','m','f')
                UNION ALL SELECT pronamespace FROM pg_proc
                UNION ALL SELECT typnamespace FROM pg_type WHERE typtype IN ('c','d','e','r','m')
            ) objects JOIN pg_namespace n ON n.oid=objects.namespace
            WHERE left(n.nspname,3) <> 'pg_' AND n.nspname <> 'information_schema'
        """).fetchone()[0]
            == 0
        )


def _verify(source, manifest):
    if (
        manifest.get("formatVersion") != 1
        or manifest.get("component") != "heteroes-product-metadata"
        or manifest.get("databaseDriver") != "postgresql"
        or manifest.get("dumpFormat") != "custom"
        or manifest.get("pgDumpMajor") != 17
        or not isinstance(manifest.get("schemaName"), str)
        or not _SCHEMA.fullmatch(manifest["schemaName"])
    ):
        raise ValueError("Unsupported PostgreSQL metadata backup")
    with Path(source).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest.get("sha256") or Path(source).stat().st_size != manifest.get("sizeBytes"):
        raise ValueError("Metadata checksum mismatch")


def _restore_sql(source, destination, schema):
    # pg_restore emits CREATE SCHEMA for a selected schema, while a fresh DB already has public. Make only this
    # pre-data DDL idempotent; do not transform COPY data, business SQL or the application's schema definition.
    creations = {f"CREATE SCHEMA {schema};".encode(), f'CREATE SCHEMA "{schema}";'.encode()}
    data_started = False
    with Path(source).open("rb") as original, Path(destination).open("xb") as output:
        os.chmod(destination, 0o600)
        for line in original:
            if line.startswith(b"COPY "):
                data_started = True
            if not data_started and line.strip() in creations:
                line = f'CREATE SCHEMA IF NOT EXISTS "{schema}";\n'.encode()
            output.write(line)
        output.write(
            (
                '''
SET search_path TO "'''
                + schema
                + """",pg_catalog;
DO $held_restore$ BEGIN
    IF (SELECT value FROM settings WHERE key='controlMode') IS DISTINCT FROM 'agent-v2' THEN
        RAISE EXCEPTION 'Expected agent metadata';
    END IF;
    IF (SELECT max(version) FROM schema_versions) IS DISTINCT FROM 1::bigint THEN
        RAISE EXCEPTION 'Unsupported metadata version';
    END IF;
END $held_restore$;
DELETE FROM sessions;
DELETE FROM cloud_downloads;
INSERT INTO settings(key,value) VALUES ('dispatchHold','true')
    ON CONFLICT(key) DO UPDATE SET value=excluded.value;
"""
            ).encode()
        )


def restore_postgres(source, manifest, database):
    _verify(source, manifest)
    if database.dialect != "postgresql":
        raise ValueError("PostgreSQL restore requires PostgreSQL")
    if not _empty(database):
        raise ValueError("Restore requires an empty target database")
    restore, _ = _tool("HETEROES_PG_RESTORE", "pg_restore")
    psql, _ = _tool("HETEROES_PSQL", "psql")
    environment = postgres_environment(database.url)
    with database.engine.connect() as physical:
        physical.detach()
        held = physical.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": LAB_WRITE_LOCK})
        physical.commit()
        if not held:
            raise ValueError("Restore target database is in use")
        try:
            with database.use_session(physical):
                if not _empty(database):
                    raise ValueError("Restore requires an empty target database")
                with TemporaryDirectory(prefix="heteroes-pg-restore-", dir=Path(source).parent) as temporary:
                    root = Path(temporary)
                    raw, sql = root / "archive.sql", root / "held.sql"
                    descriptor = os.open(raw, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(descriptor)
                    _run([restore, "--no-owner", "--no-privileges", "--file=" + str(raw), str(source)])
                    _restore_sql(raw, sql, manifest["schemaName"])
                    # The data and quarantine commit together; an invalid backup leaves the target empty.
                    _run(
                        [
                            psql,
                            "-X",
                            "--no-password",
                            "--single-transaction",
                            "--set=ON_ERROR_STOP=1",
                            "--file=" + str(sql),
                        ],
                        environment,
                    )
        finally:
            try:
                physical.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LAB_WRITE_LOCK}).close()
                physical.commit()
            finally:
                physical.close()
    return {
        "restored": True,
        "dispatchHeld": True,
        "sessionsRevoked": True,
        "reservationsPreserved": True,
        "schemaName": manifest["schemaName"],
    }
