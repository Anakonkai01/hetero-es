"""The production factory has one control mode and preserves shipped app capabilities."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import app_from_environment
from backend.devices import AgentRuntime
from backend.server import initialize
from backend.writer_lock import acquire_writer


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    root = tmp_path / "lab"
    initialize(
        root,
        {
            "username": "owner",
            "password": "synthetic-admin-password",
            "host": "127.0.0.1",
            "port": 8765,
            "storageDirectory": str(tmp_path / "storage"),
        },
    )
    monkeypatch.setenv("HETEROES_PRIVATE_CONFIG", str(root))
    monkeypatch.delenv("HETEROES_WEB_DIRECTORY", raising=False)
    monkeypatch.delenv("HETEROES_DOWNLOADS_DIRECTORY", raising=False)
    return root


def test_factory_requires_an_explicit_private_configuration(monkeypatch):
    monkeypatch.delenv("HETEROES_PRIVATE_CONFIG", raising=False)
    with pytest.raises(ValueError, match="HETEROES_PRIVATE_CONFIG"):
        app_from_environment()


@pytest.mark.parametrize("mode", ["legacy", None])
def test_non_agent_configuration_is_rejected_and_releases_writer(deployment, mode):
    path = deployment / "config.json"
    config = json.loads(path.read_text())
    if mode is None:
        config.pop("deploymentMode")
    else:
        config["deploymentMode"] = mode
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="agent"):
        app_from_environment()
    with acquire_writer(deployment / "state/product.sqlite"):
        pass


def test_agent_factory_keeps_r10_health_and_installs_device_routes(deployment):
    app = app_from_environment()
    assert isinstance(app.state.store.runtime, AgentRuntime)
    with TestClient(app) as client:
        health = client.get("/api/v1/health").json()
        assert health["agentMode"] is True
        assert health["deviceConfiguration"] is True
        assert health["recipeVersions"] == [1, 2]
        assert client.get("/api/v1/devices").status_code == 401


def test_cloud_configuration_cannot_silently_disable_recovery(deployment):
    path = deployment / "config.json"
    config = json.loads(path.read_text())
    config.update(storageMode="cloud", storageFile="/retired-provider.json")
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="local"):
        app_from_environment()
