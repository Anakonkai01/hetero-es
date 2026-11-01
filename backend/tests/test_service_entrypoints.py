"""Container roles have usable CLI entrypoints and enforce PostgreSQL before starting split production services."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend.apps.factory import app_from_environment


def _private(root, identity="c" * 32):
    root.mkdir()
    (root / "config.json").write_text(
        json.dumps(
            {
                "deploymentMode": "agent",
                "storageMode": None,
                "productStateDirectory": str(root / "state"),
                "serverInstanceId": identity,
            }
        )
    )
    (root / "credentials.json").write_text('{"users":{}}')


def test_every_service_has_a_module_entrypoint():
    for role in ("all", "api", "devices", "storage", "scheduler"):
        completed = subprocess.run(
            [sys.executable, "-m", "backend.apps." + role, "--help"], capture_output=True, text=True
        )
        assert completed.returncode == 0 and "--port" in completed.stdout


def test_split_production_roles_require_postgresql(tmp_path, monkeypatch):
    root = tmp_path / "private"
    _private(root)
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(root))
    monkeypatch.delenv("HETEROES_DATABASE_URL", raising=False)
    for role in ("api", "devices", "storage", "scheduler"):
        with pytest.raises(ValueError, match="PostgreSQL"):
            app_from_environment(service=role)
    assert not (root / "state/product.sqlite").exists()


if os.environ.get("HETEROES_TEST_DATABASE_URL"):

    def test_two_production_api_factories_share_postgresql_without_a_local_writer_lock(lab, tmp_path, monkeypatch):
        _, store, runtime, _ = lab
        with store.db() as db:
            schema = db.execute("SELECT current_schema()").fetchone()[0]
        target = store.database.url.set(query={"options": "-csearch_path=" + schema})
        root = tmp_path / "private"
        _private(root, runtime.server_instance_id)
        monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(root))
        monkeypatch.setenv("HETEROES_DATABASE_URL", target.render_as_string(hide_password=False))
        monkeypatch.setenv("HETEROES_SERVICE", "api")
        first, second = app_from_environment(), app_from_environment()
        try:
            assert first.state.service == second.state.service == "api"
            assert first.state.store.database.dialect == second.state.store.database.dialect == "postgresql"
            assert (
                first.state.store.runtime.server_instance_id
                == second.state.store.runtime.server_instance_id
                == runtime.server_instance_id
            )
            assert not (root / "state/product.sqlite").exists()
        finally:
            first.state.store.close()
            second.state.store.close()
