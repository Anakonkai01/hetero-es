"""Split HTTP processes own an exact, disjoint partition of the combined product contract."""

from collections import Counter
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import threading

from fastapi.testclient import TestClient
import pytest

from backend.apps.factory import create_app
from backend.apps.routing import inventory
from backend.services.devices import AgentRuntime
from backend.services.store import Store
from backend.services.scheduler_controller import SchedulerController
from backend.storage.local_backend import LocalBackend

BASELINE = json.loads(
    (
        Path(__file__).parent
        / "fixtures/archive/docs/evidence/2026-11-01-backend-inventory/route-ownership-proposal.json"
    ).read_text()
)
OPERATIONAL = {("GET", "/healthz"), ("GET", "/readyz"), ("GET", "/metrics")}


def _application(tmp_path, service, storage, web, dispatch=False):
    web_root = tmp_path / "web"
    if web:
        (web_root / "assets").mkdir(parents=True, exist_ok=True)
        (web_root / "index.html").write_text("<!doctype html><title>Fixture</title>")
    downloads = tmp_path / "downloads"
    downloads.mkdir(exist_ok=True)
    backend = (
        LocalBackend(tmp_path / "objects", tmp_path / "signing.key", "http://127.0.0.1:18052") if storage else None
    )
    return create_app(
        tmp_path / "product.sqlite",
        {},
        AgentRuntime(backend),
        dispatch=dispatch,
        service=service,
        web_directory=web_root if web else None,
        downloads_directory=downloads if web else None,
    )


@pytest.mark.parametrize("storage,web", [(True, True), (True, False), (False, True), (False, False)])
def test_route_partition_is_exact_and_nonoverlapping_for_matching_features(tmp_path, storage, web):
    with ExitStack() as cleanup:
        applications = {
            role: _application(tmp_path, role, storage, web)
            for role in ("all", "api", "devices", "storage", "scheduler")
        }
        for app in applications.values():
            cleanup.callback(app.state.store.close)
        contracts = {role: inventory(app) for role, app in applications.items()}
        product = lambda contract: {(row["method"], row["path"]) for row in contract["product"]}
        all_routes = product(contracts["all"])
        owned = [pair for role in ("api", "devices", "storage") for pair in product(contracts[role])]
        assert len(owned) == len(set(owned)) and set(owned) == all_routes
        assert product(contracts["scheduler"]) == set()
        for role, contract in contracts.items():
            assert {(row["method"], row["path"]) for row in contract["operational"]} == OPERATIONAL
            if role in ("devices", "storage", "scheduler"):
                assert contract["mounts"] == []
        if storage and web:
            expected = {(method, row["path"]): row["owner"] for row in BASELINE for method in row.get("methods", [])}
            assert len(all_routes) == 111 and all_routes == set(expected)
            assert {role: len(product(contracts[role])) for role in ("api", "devices", "storage")} == {
                "api": 67,
                "devices": 21,
                "storage": 23,
            }
            for role in ("api", "devices", "storage"):
                assert all(expected[pair] == role for pair in product(contracts[role]))
            assert {row["path"] for row in contracts["all"]["mounts"]} == {"/assets", "/downloads"}
            assert contracts["all"]["mounts"] == contracts["api"]["mounts"]


def test_diagnostics_precede_the_spa_and_unowned_routes_remain_absent(tmp_path):
    with ExitStack() as cleanup:
        for role in ("all", "api", "devices", "storage", "scheduler"):
            app = _application(tmp_path, role, True, True)
            with TestClient(app) as client:
                assert client.get("/healthz").json()["service"] == role
                assert client.get("/readyz").json()["ready"] is True
                assert "heteroes_service_up" in client.get("/metrics").text
                if role != "all":
                    forbidden = "/api/v1/auth/login" if role != "api" else "/api/v1/device/enroll"
                    # The API keeps the existing GET SPA catch-all, which reports 405 for unknown POST methods.
                    assert client.post(forbidden, json={}).status_code == (405 if role == "api" else 404)


def test_api_and_device_processes_start_no_dispatch_or_backup_loops(tmp_path, monkeypatch):
    started = []
    dispatch_started = threading.Event()

    def dispatch(store, stop):
        started.append("dispatch")
        dispatch_started.set()
        stop.wait(3)

    def backup(store, storage, stop):
        started.append("backup")
        stop.wait(3)

    monkeypatch.setattr(SchedulerController, "run", dispatch)
    monkeypatch.setattr("backend.services.metadata_backup.backup_loop", backup)
    for role in ("api", "devices"):
        with TestClient(_application(tmp_path, role, True, False, dispatch=True)):
            assert not dispatch_started.wait(0.05)
            assert started == []
    with TestClient(_application(tmp_path, "storage", True, False, dispatch=True)):
        pass
    assert started == ["backup"]


def test_route_export_is_machine_readable_and_uses_only_isolated_state():
    completed = subprocess.run(
        [sys.executable, "-m", "backend.apps.routes", "--json"], check=True, capture_output=True, text=True
    )
    contract = json.loads(completed.stdout)
    assert contract["version"] == 1
    assert Counter(row["owner"] for row in contract["product"]) == {"api": 67, "devices": 21, "storage": 23}
    assert len(contract["product"]) == 111
    assert contract["mounts"] == [{"path": "/assets", "owner": "api"}, {"path": "/downloads", "owner": "api"}]
