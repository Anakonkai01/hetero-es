"""Fixtures for the backend tests: agent-mode labs with a CPU-only fake GPU profile (helpers in labkit.py)."""
from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.devices import AgentRuntime
from labkit import USERS, enable, login, pair


@pytest.fixture
def lab(tmp_path):
    """An agent-mode lab without devices and with one user, the administrator: (client, store, runtime, admin headers)."""
    runtime = AgentRuntime()
    app = create_app(tmp_path / 'lab.sqlite', {'admin': USERS['admin']}, runtime, dispatch=False)
    with TestClient(app) as client:
        yield client, app.state.store, runtime, login(client, 'admin')


@pytest.fixture
def setup(tmp_path):
    """An agent-mode lab with the users admin and participant and two approved devices that are online and contribute:
    '5070ti' and '3060', both coordinator-capable. Yields (client, store, runtime)."""
    runtime = AgentRuntime()
    app = create_app(tmp_path / 'product.sqlite', USERS, runtime, dispatch=False)
    with TestClient(app) as client:
        kit = (client, app.state.store, runtime, login(client, 'admin'))
        for alias in ('5070ti', '3060'):
            enable(kit, *pair(kit, alias))
        yield client, app.state.store, runtime
