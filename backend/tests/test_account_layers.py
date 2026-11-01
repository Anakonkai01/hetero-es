"""Account services retain durable auth behavior without an HTTP or SQL dependency in the wrong layer."""

import ast
import hashlib
from pathlib import Path
import time

import pytest

from backend.core.errors import ServiceError
from backend.services.accounts import AccountService
from backend.devices import AgentRuntime
from backend.store import Store


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
    for relative in ("api/auth.py", "api/accounts.py", "api/security.py", "services/accounts.py"):
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
