"""Isolated, real database owners shared by portable engine/schema/repository tests."""

from contextlib import ExitStack
import os
import uuid

import pytest

from backend.db.engine import Database

_DIALECTS = ["sqlite"] + (["postgresql"] if os.environ.get("HETEROES_TEST_DATABASE_URL") else [])


@pytest.fixture(params=_DIALECTS)
def database(request, tmp_path):
    with ExitStack() as cleanup:
        options = {}
        if request.param == "sqlite":
            target = tmp_path / "engine.sqlite"
        else:
            target = os.environ["HETEROES_TEST_DATABASE_URL"]
            administrator = Database(target)
            cleanup.callback(administrator.close)
            schema = "engine_test_" + uuid.uuid4().hex
            with administrator.transaction() as connection:
                connection.execute("CREATE SCHEMA " + schema)

            def drop_schema():
                with administrator.transaction() as connection:
                    connection.execute("DROP SCHEMA " + schema + " CASCADE")

            cleanup.callback(drop_schema)
            # A broken nested-transaction implementation must fail instead of waiting indefinitely on itself.
            options = {"options": "-csearch_path=" + schema + " -clock_timeout=2000"}
        owner = Database(target, connect_args=options)
        cleanup.callback(owner.close)
        with owner.transaction() as connection:
            connection.execute("CREATE TABLE entries(id BIGINT PRIMARY KEY,value TEXT,enabled BIGINT,large BIGINT)")
        yield owner, lambda: Database(target, connect_args=options)


@pytest.fixture(autouse=True)
def product_database_target(request, monkeypatch):
    """Point every ordinary Store at real PostgreSQL; explicit SQLite file contracts keep their real files.

    Each logical product path gets one private schema per test, so reopened Store facades share state while separate
    labs stay isolated. Production code never reads this test-only variable and no dummy SQLite file is created.
    """
    from backend.services.store import Store

    target = os.environ.get("HETEROES_TEST_DATABASE_URL")
    sqlite_contract = request.node.get_closest_marker("sqlite_file") is not None
    schemas, stores = {}, []
    administrator = Database(target) if target and not sqlite_contract else None
    original = Store.__init__
    audit = getattr(request.config, "_heteroes_database_audit", None)
    if audit is None:
        audit = {"productStores": {"sqlite": 0, "postgresql": 0}, "tests": {}, "explicitSQLiteContracts": []}
        request.config._heteroes_database_audit = audit

    def initialize(store, path, passwords, runtime, **options):
        if administrator is not None and not options.get("database_url"):
            logical_path = str(path)
            if logical_path not in schemas:
                schema = "product_test_" + uuid.uuid4().hex
                with administrator.transaction() as db:
                    db.execute("CREATE SCHEMA " + schema)
                schemas[logical_path] = schema
            options.update(
                database_url=target,
                database_connect_args={
                    "options": "-csearch_path="
                    + schemas[logical_path]
                    + " -clock_timeout=15000 -cstatement_timeout=30000"
                },
            )
        stores.append(store)
        original(store, path, passwords, runtime, **options)
        dialect = store.database.dialect
        if target and not sqlite_contract:
            assert dialect == "postgresql", "An ordinary product fixture failed to select PostgreSQL"
        audit["productStores"][dialect] += 1
        audit["tests"].setdefault(request.node.nodeid, []).append(dialect)
        if sqlite_contract and request.node.nodeid not in audit["explicitSQLiteContracts"]:
            audit["explicitSQLiteContracts"].append(request.node.nodeid)

    monkeypatch.setattr(Store, "__init__", initialize)
    try:
        yield
    finally:
        for store in stores:
            database_owner = getattr(store, "database", None)
            if database_owner is not None:
                database_owner.close()
        if administrator is not None:
            try:
                with administrator.transaction() as db:
                    for schema in schemas.values():
                        db.execute("DROP SCHEMA " + schema + " CASCADE")
            finally:
                administrator.close()


@pytest.fixture
def fresh_postgres_database():
    """Create/drop only this test's fresh databases in the explicit owned PostgreSQL test server."""
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    target = make_url(os.environ["HETEROES_TEST_DATABASE_URL"])
    created = []
    with Database(target) as administration:

        def create():
            name = "backup_restore_test_" + uuid.uuid4().hex
            with administration.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
                db.execute(text("CREATE DATABASE " + name))
            created.append(name)
            return target.set(database=name, query={})

        try:
            yield create
        finally:
            for name in created:
                with administration.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
                    db.execute(text("DROP DATABASE " + name + " WITH (FORCE)"))
