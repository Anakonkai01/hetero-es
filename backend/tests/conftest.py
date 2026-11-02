"""Fixtures for the backend tests: agent-mode labs with a CPU-only fake GPU profile (helpers in labkit.py)."""

from fastapi.testclient import TestClient
import pytest

from dbkit import (
    database as database,
    product_database_target as product_database_target,
    fresh_postgres_database as fresh_postgres_database,
)

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from labkit import USERS, enable, login, pair


@pytest.fixture
def lab(tmp_path):
    """An agent-mode lab without devices and with one user, the administrator: (client, store, runtime, admin headers)."""
    runtime = AgentRuntime()
    app = create_app(tmp_path / "lab.sqlite", {"admin": USERS["admin"]}, runtime, dispatch=False)
    with TestClient(app) as client:
        yield client, app.state.store, runtime, login(client, "admin")


@pytest.fixture
def setup(tmp_path):
    """An agent-mode lab with the users admin and participant and two approved devices that are online and contribute:
    '5070ti' and '3060', both coordinator-capable. Yields (client, store, runtime)."""
    runtime = AgentRuntime()
    app = create_app(tmp_path / "product.sqlite", USERS, runtime, dispatch=False)
    with TestClient(app) as client:
        kit = (client, app.state.store, runtime, login(client, "admin"))
        for alias in ("5070ti", "3060"):
            enable(kit, *pair(kit, alias))
        yield client, app.state.store, runtime


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "sqlite_file: explicit legacy SQLite file-format, migration, backup or local deployment contract"
    )


def pytest_sessionfinish(session, exitstatus):
    import json
    import os
    from pathlib import Path

    destination = os.environ.get("HETEROES_TEST_DATABASE_AUDIT_FILE")
    audit = getattr(session.config, "_heteroes_database_audit", None)
    if destination and audit is not None:
        Path(destination).write_text(json.dumps(audit, indent=2) + "\n")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    audit = getattr(config, "_heteroes_database_audit", None)
    if audit is not None:
        counts = audit["productStores"]
        terminalreporter.write_line(
            f"Product database targets: PostgreSQL {counts['postgresql']}, SQLite {counts['sqlite']}; "
            f"explicit SQLite file contracts {len(audit['explicitSQLiteContracts'])}."
        )
