"""The Store facade keeps transaction semantics while its DB owner handles persistence."""

import ast
from pathlib import Path
import pytest

from backend.devices import AgentRuntime
from backend.store import Store


def test_sql_execution_is_owned_by_database_and_repositories():
    backend = Path(__file__).resolve().parents[1]
    for path in backend.rglob("*.py"):
        relative = path.relative_to(backend)
        if relative.parts[0] in {"tests", "db", "repositories"}:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call):
                operation = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else None
                )
                assert operation not in {"execute", "executescript", "executemany", "backup"}, (
                    str(relative),
                    operation,
                )


def test_store_context_commits_and_rolls_back_with_the_same_audit_boundary(tmp_path):
    store = Store(tmp_path / "transactions.sqlite", {"admin": "store-fixture-password"}, AgentRuntime())
    with pytest.raises(RuntimeError, match="rollback fixture"):
        with store.db() as db:
            db.execute("INSERT INTO settings VALUES (?,?)", ("rollback-fixture", "true"))
            store.audit(db, "admin", "ROLLBACK_FIXTURE", "entry")
            raise RuntimeError("rollback fixture")
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM settings WHERE key=?", ("rollback-fixture",)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM audit WHERE action=?", ("ROLLBACK_FIXTURE",)).fetchone()[0] == 0
        db.execute("INSERT INTO settings VALUES (?,?)", ("commit-fixture", "true"))
        store.audit(db, "admin", "COMMIT_FIXTURE", "entry")
    with store.db() as db:
        assert db.execute("SELECT value FROM settings WHERE key=?", ("commit-fixture",)).fetchone()[0] == "true"
        assert db.execute("SELECT count(*) FROM audit WHERE action=?", ("COMMIT_FIXTURE",)).fetchone()[0] == 1


def test_borrowed_connection_is_unusable_after_its_transaction_scope(tmp_path):
    store = Store(tmp_path / "lifetime.sqlite", {"admin": "store-fixture-password"}, AgentRuntime())
    with store.db() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(Exception):
        connection.execute("SELECT 1")


def test_store_uses_the_core_owner_and_nested_reads_share_uncommitted_state(tmp_path):
    from backend.db.engine import Database

    store = Store(tmp_path / "core-owner.sqlite", {"admin": "store-fixture-password"}, AgentRuntime())
    try:
        assert isinstance(store.database, Database)
        with store.db() as db:
            db.execute("UPDATE users SET profile=:p0 WHERE id=:p1", ('{"userId":"admin","fixture":true}', "admin"))
            assert store.profile("admin") == {"userId": "admin", "fixture": True}
            with store.db() as nested:
                assert nested is db
    finally:
        store.close()
