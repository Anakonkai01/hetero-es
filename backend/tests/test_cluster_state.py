"""Cloud replicas share cluster identity and scheduler diagnostics; local desktop state keeps its old lifetime."""

from fastapi.testclient import TestClient
import pytest

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from backend.services.store import Store


def _runtime(identifier=None):
    runtime = AgentRuntime()
    runtime.server_instance_id = identifier
    return runtime


def test_replicas_publish_the_same_identity_and_durable_scheduler_failure(tmp_path):
    path, identity = tmp_path / "replicas.sqlite", "a" * 32
    first = create_app(path, {}, _runtime(identity), dispatch=False, service="api")
    first.state.store.last_error = "ConnectionError"
    second = create_app(path, {}, _runtime(identity), dispatch=False, service="api")
    cloud = first.state.store.database.dialect == "postgresql"
    try:
        with TestClient(first) as client_one, TestClient(second) as client_two:
            one, two = client_one.get("/api/v1/health").json(), client_two.get("/api/v1/health").json()
            assert one["serverInstanceId"] == two["serverInstanceId"] == identity
            assert one["runtimeIssue"] == "ConnectionError"
            assert two["runtimeIssue"] == ("ConnectionError" if cloud else None)
            second.state.store.last_error = None
            assert client_one.get("/api/v1/health").json()["runtimeIssue"] == (None if cloud else "ConnectionError")
        if cloud:
            restarted = Store(path, {}, _runtime())
            try:
                assert restarted.runtime.server_instance_id == identity
                assert restarted.last_error is None
            finally:
                restarted.close()
    finally:
        first.state.store.close()
        second.state.store.close()


def test_cloud_replicas_reject_conflicting_configured_identity(tmp_path):
    path = tmp_path / "identity.sqlite"
    original = Store(path, {}, _runtime("a" * 32))
    try:
        if original.database.dialect == "postgresql":
            with pytest.raises(ValueError, match="identity"):
                Store(path, {}, _runtime("b" * 32))
        else:
            local = Store(path, {}, _runtime("b" * 32))
            try:
                assert local.runtime.server_instance_id == "b" * 32
            finally:
                local.close()
    finally:
        original.close()
