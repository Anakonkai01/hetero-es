"""Account services retain durable auth behavior without an HTTP or SQL dependency in the wrong layer."""

import ast
import hashlib
from pathlib import Path
import time

import pytest

from backend.core.errors import ServiceError
from backend.services.accounts import AccountService
from backend.services.devices import AgentRuntime
from backend.services.store import Store


def test_session_lookup_checks_expiry_and_revocation_from_durable_state(tmp_path):
    store = Store(tmp_path / "accounts.sqlite", {"admin": "test-admin-pass"}, AgentRuntime())
    service = AccountService(store)
    token = "test-session-value"
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.db() as db:
        db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest, "admin", time.time() - 60))
    with pytest.raises(ServiceError) as expired:
        service.current(token)
    assert expired.value.status_code == 401
    with store.db() as db:
        db.execute("UPDATE sessions SET expires=? WHERE digest=?", (time.time() + 60, digest))
    assert service.current(token)["userId"] == "admin"
    service.sign_out(token)
    with pytest.raises(ServiceError) as revoked:
        service.current(token)
    assert revoked.value.status_code == 401


def test_service_errors_are_plain_errors_and_keep_public_message_headers():
    error = ServiceError(429, "Try again later", headers={"Retry-After": "30"})
    assert isinstance(error, Exception)
    assert not any(base.__module__.startswith(("fastapi", "starlette")) for base in type(error).__mro__)
    assert error.status_code == 429 and error.detail == "Try again later"
    assert error.headers == {"Retry-After": "30"}


def test_account_layer_boundaries():
    backend = Path(__file__).resolve().parents[1]
    for relative in sorted(
        path.relative_to(backend).as_posix()
        for group in ("api", "services", "core", "storage")
        for path in (backend / group).rglob("*.py")
    ):
        tree = ast.parse((backend / relative).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"execute", "executemany", "executescript"}, relative
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if relative.startswith("api/"):
                    assert not module.startswith(("repositories", "db")), (relative, module)
                else:
                    assert not module.startswith(("fastapi", "starlette")), (relative, module)
            if isinstance(node, ast.Import) and relative.startswith("services/"):
                assert not any(n.name.startswith(("fastapi", "starlette")) for n in node.names)


def test_repository_conflict_is_translated_without_exposing_driver_errors():
    import sqlite3

    from backend.core.errors import DatabaseConflict
    from backend.repositories.base import execute

    with sqlite3.connect(":memory:") as db:
        execute(db, "CREATE TABLE entries(id TEXT PRIMARY KEY)")
        execute(db, "INSERT INTO entries VALUES (?)", ("same",))
        with pytest.raises(DatabaseConflict):
            execute(db, "INSERT INTO entries VALUES (?)", ("same",))
        assert execute(db, "SELECT count(*) FROM entries").fetchone()[0] == 1


def test_explicit_write_transaction_rolls_back_uncommitted_changes():
    import sqlite3

    from backend.db.transactions import begin_write

    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE changes(id INTEGER)")
        begin_write(db)
        db.execute("INSERT INTO changes VALUES (1)")
        db.rollback()
        assert db.execute("SELECT count(*) FROM changes").fetchone()[0] == 0


def test_template_service_uses_plain_errors_and_legacy_helper_keeps_http_errors():
    from fastapi import HTTPException

    from backend.api.templates import clean_config as http_config
    from backend.services.templates import clean_config as service_config

    valid = {"maxGenerations": 3, "workerIds": ["5070ti"]}
    assert service_config(valid) == http_config(valid) == valid
    with pytest.raises(ServiceError) as business:
        service_config({"modelArtifactId": "not-a-portable-setting"})
    with pytest.raises(HTTPException) as legacy:
        http_config({"modelArtifactId": "not-a-portable-setting"})
    assert business.value.status_code == legacy.value.status_code == 422
    assert business.value.detail == legacy.value.detail
