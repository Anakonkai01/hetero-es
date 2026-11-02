"""Operational metrics/logging expose bounded route labels and fresh business observations, never credentials."""

import json
from pathlib import Path
import re
import time

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families
import pytest

from backend.apps.factory import create_app
from backend.services.devices import AgentRuntime
from backend.storage.local_backend import LocalBackend


def samples(text, name):
    return [
        sample for family in text_string_to_metric_families(text) for sample in family.samples if sample.name == name
    ]


@pytest.fixture
def observed(tmp_path):
    storage = LocalBackend(tmp_path / "objects", tmp_path / "private/key", "http://127.0.0.1:18052")
    app = create_app(tmp_path / "product.sqlite", {}, AgentRuntime(storage), dispatch=False)
    with TestClient(app) as client:
        yield client, app


def test_http_metrics_and_json_logs_use_only_route_patterns_and_generated_request_ids(observed, capsys):
    client, app = observed
    secret = "never-publish-credential-marker"
    assert (
        client.get(
            "/healthz?access_token=" + secret, headers={"Authorization": "Bearer " + secret, "X-Request-Id": secret}
        ).status_code
        == 200
    )
    response = client.get("/api/v1/local-storage/" + secret)
    assert response.status_code == 403
    assert client.post("/api/v1/auth/login", json={"username": "missing", "password": secret}).status_code == 401
    assert client.get("/unmatched/" + secret).status_code == 404
    response = client.get("/metrics")
    assert response.status_code == 200
    assert secret not in response.text
    requests = samples(response.text, "heteroes_http_requests_total")
    routes = {row.labels["route"] for row in requests}
    assert "/healthz" in routes and "/api/v1/local-storage/{token}" in routes and "/api/v1/auth/login" in routes
    assert "_unmatched" in routes
    assert all(set(row.labels) == {"service", "method", "route", "status"} for row in requests)
    assert len(requests) == 4 and all(row.value == 1 for row in requests)
    assert samples(response.text, "heteroes_http_request_duration_seconds_count")
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    lines = [json.loads(line) for line in captured.out.splitlines() if line]
    assert len(lines) == 5
    assert all(
        set(row) == {"ts", "level", "service", "method", "route", "status", "duration_ms", "request_id"}
        for row in lines
    )
    assert all(re.fullmatch("[a-f0-9]{32}", row["request_id"]) and row["duration_ms"] >= 0 for row in lines)
    assert response.headers["x-request-id"] == lines[-1]["request_id"]
    assert not samples(response.text, "heteroes_runs")
    assert client.get("/healthz").status_code == 200
    repeated = samples(client.get("/metrics").text, "heteroes_http_requests_total")
    assert next(row.value for row in repeated if row.labels["route"] == "/healthz") == 2


def test_ready_checks_storage_and_hides_exception_details(observed, monkeypatch, capsys):
    client, app = observed
    assert client.get("/readyz").status_code == 200

    def unavailable():
        raise RuntimeError("never-publish-storage-detail")

    monkeypatch.setattr(app.state.storage.backend, "ready", unavailable)
    response = client.get("/readyz")
    assert response.status_code == 503 and response.json()["ready"] is False
    assert "never-publish" not in response.text + capsys.readouterr().out
    assert client.get("/healthz").status_code == 200


def test_unhandled_error_is_logged_once_as_safe_json_without_raw_error_or_request_data(tmp_path, capsys):
    app = create_app(tmp_path / "error.sqlite", {}, AgentRuntime(), dispatch=False)

    @app.get("/fixture-error/{identifier}")
    def fail(identifier: str):
        raise RuntimeError("never-publish-exception-detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/fixture-error/never-publish-path?password=never-publish-query")
        assert response.status_code == 500
    captured = capsys.readouterr()
    assert "never-publish" not in captured.out + captured.err + response.text
    lines = [json.loads(line) for line in captured.out.splitlines() if line]
    assert len(lines) == 1 and lines[0]["route"] == "/fixture-error/{identifier}" and lines[0]["status"] == 500
    assert lines[0]["level"] == "ERROR"


def test_scheduler_business_snapshot_is_fresh_and_omits_unknown_gpu_values(tmp_path):
    from types import SimpleNamespace

    app = create_app(tmp_path / "scheduler.sqlite", {}, AgentRuntime(), dispatch=False, service="scheduler")
    store = app.state.store
    from backend.services.observability import BusinessSnapshot

    clock = time.time()
    device = "a" * 32
    telemetry = {
        "sampledAt": clock,
        "gpu": {
            "utilizationPercent": 37.5,
            "temperatureC": 62,
            "vramUsedMb": 12.5,
            "vramTotalMb": 24,
            "powerDrawW": None,
        },
    }
    body = {
        "experimentId": "b" * 32,
        "workspaceId": "lab",
        "ownerUserId": "owner",
        "status": "COMPLETED",
        "completedGenerations": 3,
    }
    snapshot = {
        "attempts": [
            {"status": "FAILED", "errorType": "RESTORE_MISMATCH"},
            {"status": "FAILED", "errorType": "never-publish-error-type"},
        ]
    }
    with store.db() as db:
        db.execute(
            "INSERT INTO devices(id,worker_id,owner,name,token_digest,status,compute_url,self_test,seen,telemetry) VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9)",
            (
                device,
                "worker",
                "owner",
                "never-publish-device-name",
                "digest",
                "APPROVED",
                "http://127.0.0.1:18053",
                "{}",
                clock,
                json.dumps(telemetry),
            ),
        )
        db.execute(
            "INSERT INTO experiments(id,owner,body,snapshot) VALUES (:p0,:p1,:p2,:p3)",
            (body["experimentId"], "owner", json.dumps(body), json.dumps(snapshot)),
        )
        db.execute("INSERT INTO queue(run_id) VALUES (:p0)", (body["experimentId"],))
        db.execute("INSERT INTO cloud_objects(sha,size,status) VALUES (:p0,128,:p1)", ("c" * 64, "READY"))
        db.execute("INSERT INTO cloud_objects(sha,size,status) VALUES (:p0,64,:p1)", ("d" * 64, "UPLOADING"))
    first = BusinessSnapshot(store, SimpleNamespace(quota=1024)).capture()
    assert first["devices"]["APPROVED"] == 1 and first["online"] == 1 and first["queue"] == 1
    assert first["runs"]["COMPLETED"] == 1 and first["generations"] == 3
    assert first["errors"] == {"RESTORE_MISMATCH": 1, "OTHER": 1}
    assert first["storage_bytes"] == 128 and first["reserved_bytes"] == 128 and first["quota_bytes"] == 1024
    with store.db() as db:
        db.execute("DELETE FROM queue")
    assert BusinessSnapshot(store).capture()["queue"] == 0
    body["completedGenerations"] = 10**400
    with store.db() as db:
        db.execute("UPDATE experiments SET body=:p0", (json.dumps(body),))
    assert BusinessSnapshot(store).capture()["generations"] == 0

    store.close()


@pytest.mark.parametrize("role", ["all", "api", "devices", "storage"])
def test_non_scheduler_never_collects_business_state(tmp_path, monkeypatch, role):
    app = create_app(tmp_path / "non-scheduler.sqlite", {}, AgentRuntime(), dispatch=False, service=role)
    from backend.services.observability import BusinessSnapshot

    def forbidden(self):
        raise AssertionError("API/all role must not query business metrics")

    monkeypatch.setattr(BusinessSnapshot, "capture", forbidden)
    monkeypatch.setattr(app.state.scheduler, "read_metrics", lambda read: forbidden(None))
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 200


@pytest.mark.sqlite_file
def test_desktop_local_mode_keeps_basic_metrics_without_optional_cloud_library(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    app = create_app(tmp_path / "desktop.sqlite", {}, AgentRuntime(), dispatch=False)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/metrics")
        assert response.status_code == 200 and "heteroes_service_up" in response.text
    with pytest.raises(ValueError, match="metrics dependency"):
        create_app(tmp_path / "cloud.sqlite", {}, AgentRuntime(), dispatch=False, service="api")


def test_gpu_metric_units_and_missing_observations_are_preserved(tmp_path):
    from contextlib import ExitStack
    from backend.db.leadership import SchedulerLeader

    app = create_app(tmp_path / "gpu.sqlite", {}, AgentRuntime(), dispatch=False, service="scheduler")
    store = app.state.store
    device = "d" * 32
    clock = time.time()
    telemetry = {
        "sampledAt": clock,
        "gpu": {
            "utilizationPercent": 37.5,
            "temperatureC": 62,
            "vramUsedMb": 12.5,
            "vramTotalMb": 24,
            "powerDrawW": None,
            "name": "never-publish-gpu-name",
        },
    }
    with store.db() as db:
        db.execute(
            "INSERT INTO devices(id,worker_id,owner,name,token_digest,status,compute_url,self_test,seen,telemetry) VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9)",
            (
                device,
                "worker",
                "owner",
                "never-publish-name",
                "digest",
                "APPROVED",
                "http://127.0.0.1:18053",
                "{}",
                clock,
                json.dumps(telemetry),
            ),
        )
    with ExitStack() as cleanup:
        client = cleanup.enter_context(TestClient(app))
        if store.database.dialect == "postgresql":
            leader = cleanup.enter_context(SchedulerLeader(store.database))
            assert leader.try_acquire()
            app.state.scheduler._leader = leader
        app.state.scheduler.active = True
        text = client.get("/metrics").text
        assert "never-publish" not in text
        for name, value in [
            ("heteroes_gpu_utilization_percent", 37.5),
            ("heteroes_gpu_temperature_celsius", 62),
            ("heteroes_gpu_vram_used_bytes", 12.5 * 1024**2),
            ("heteroes_gpu_vram_total_bytes", 24 * 1024**2),
        ]:
            row = samples(text, name)
            assert (
                len(row) == 1
                and row[0].value == value
                and row[0].labels == {"service": "scheduler", "device_id": device}
            )
        assert samples(text, "heteroes_device_online")[0].value == 1
        assert samples(text, "heteroes_gpu_sample_timestamp_seconds")[0].value == clock
        assert not samples(text, "heteroes_gpu_power_watts")
        for invalid in (None, True, -1, 101, "never-publish-gpu-value", float("nan"), float("inf"), 10**400):
            telemetry["gpu"]["utilizationPercent"] = invalid
            with store.db() as db:
                db.execute("UPDATE devices SET telemetry=:p0 WHERE id=:p1", (json.dumps(telemetry), device))
            response = client.get("/metrics")
            assert response.status_code == 200
            assert not samples(response.text, "heteroes_gpu_utilization_percent")


def test_readiness_checks_db_and_local_directory_without_exposing_private_errors(observed, monkeypatch, capsys):
    client, app = observed

    def fail():
        raise RuntimeError("never-publish-database-detail")

    with monkeypatch.context() as patch:
        patch.setattr(app.state.store.database, "ping", fail)
        response = client.get("/readyz")
        assert response.status_code == 503
        assert "never-publish" not in response.text + capsys.readouterr().out
    app.state.storage.backend.root.rmdir()
    assert client.get("/readyz").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_untrusted_http_method_is_normalized_in_metrics_and_logs(observed, capsys):
    client, app = observed
    assert client.request("NEVER_PUBLISH_METHOD", "/healthz").status_code == 405
    text = client.get("/metrics").text
    assert any(row.labels["method"] == "OTHER" for row in samples(text, "heteroes_http_requests_total"))
    captured = capsys.readouterr()
    assert "NEVER_PUBLISH_METHOD" not in text + captured.out


def test_real_uvicorn_transport_never_logs_an_unhandled_exception_bearer():
    import selectors
    import subprocess
    import sys
    from urllib.error import HTTPError, URLError
    from urllib.request import Request
    from heteroes.http_safety import opener

    code = """
import json,socket
from types import SimpleNamespace
from fastapi import FastAPI,Request
import uvicorn
from backend.api.observability import RequestObservability
app=FastAPI()
app.add_middleware(RequestObservability,metrics=SimpleNamespace(observe=lambda *args:None),service="api")
@app.get("/fixture-error/{identifier}")
def fail(identifier:str,request:Request):raise RuntimeError(request.headers.get("authorization"))
listener=socket.socket();listener.bind(("127.0.0.1",0))
print(json.dumps({"origin":"http://127.0.0.1:"+str(listener.getsockname()[1])}),flush=True)
uvicorn.Server(uvicorn.Config(app,access_log=False,log_level="info")).run(sockets=[listener])
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    secret = "never-publish-real-http-bearer"
    body = ""
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(10), "Owned HTTP fixture did not announce its origin"
        origin = json.loads(process.stdout.readline())["origin"]
        deadline = time.monotonic() + 10
        while True:
            try:
                opener(proxy=False).open(
                    Request(origin + "/fixture-error/value", headers={"Authorization": "Bearer " + secret}), timeout=2
                )
                pytest.fail("The failing endpoint did not return500")
            except HTTPError as error:
                assert error.code == 500
                body = error.read().decode()
                break
            except URLError:
                assert time.monotonic() < deadline
                time.sleep(0.02)
    finally:
        process.terminate()
        out, err = process.communicate(timeout=10)
    assert secret not in out + err + body
    records = [json.loads(line) for line in out.splitlines() if line]
    assert len(records) == 1 and records[0]["route"] == "/fixture-error/{identifier}" and records[0]["status"] == 500
