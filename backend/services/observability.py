"""Fresh, bounded product metrics and credential-free request records; cloud instrumentation imports lazily."""

from collections import Counter
from datetime import datetime, timezone
import json
import math
import re
import sys
import threading
import time

from ..repositories.observability import ObservabilityRepository

DEVICE_STATES = ("PENDING", "APPROVED", "REVOKED", "OTHER")
RUN_STATES = (
    "DRAFT",
    "QUEUED",
    "STARTING",
    "RUNNING",
    "PAUSING",
    "PAUSED",
    "CANCELLING",
    "RECOVERING",
    "DRAINING",
    "COMPLETED",
    "CANCELLED",
    "FAILED",
    "OTHER",
)
# Ledger FailureKind plus the product's expired-lease observation; importing the numerical ledger is unnecessary.
ERROR_TYPES = frozenset({"OUT_OF_MEMORY", "VERIFIER_ERROR", "RESTORE_MISMATCH", "LEASE_EXPIRED", "OTHER"})
_LOG_LOCK = threading.Lock()


def _object(value):
    try:
        decoded = json.loads(value) if value else {}
        return decoded if isinstance(decoded, dict) else {}
    except (ValueError, TypeError):
        return {}


def _number(value, maximum=float("inf")):
    if type(value) not in {int, float}:
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= maximum else None
    except OverflowError:
        return None


class BusinessSnapshot:
    def __init__(self, store, storage=None):
        self.store, self.storage = store, storage

    def capture(self):
        with self.store.database.transaction(write=False) as db:
            rows = ObservabilityRepository.snapshot(db)
        devices, runs, errors = Counter({s: 0 for s in DEVICE_STATES}), Counter({s: 0 for s in RUN_STATES}), Counter()
        online, generations, gpu = 0, 0, []
        now = time.time()
        for row in rows["devices"]:
            status = row["status"] if row["status"] in DEVICE_STATES else "OTHER"
            devices[status] += 1
            seen = _number(row["seen"])
            connected = seen is not None and seen > now - 30
            online += int(connected)
            if re.fullmatch(r"[a-f0-9]{32}", row["id"]):
                telemetry = _object(row["telemetry"])
                observation = telemetry.get("gpu")
                gpu.append(
                    {
                        "device_id": row["id"],
                        "online": int(connected),
                        "sampled_at": _number(telemetry.get("sampledAt")),
                        "observation": observation if isinstance(observation, dict) else {},
                    }
                )
        for row in rows["experiments"]:
            body, snapshot = _object(row["body"]), _object(row["snapshot"])
            status = body.get("status")
            runs[status if isinstance(status, str) and status in RUN_STATES else "OTHER"] += 1
            completed = body.get("completedGenerations")
            if type(completed) is int and 0 <= completed <= 2**63 - 1:
                generations += completed
            attempts = snapshot.get("attempts", [])
            for attempt in attempts if isinstance(attempts, list) else []:
                if isinstance(attempt, dict) and attempt.get("status") == "FAILED":
                    kind = attempt.get("errorType")
                    errors[kind if isinstance(kind, str) and kind in ERROR_TYPES else "OTHER"] += 1
        return {
            "devices": dict(devices),
            "online": online,
            "runs": dict(runs),
            "generations": generations,
            "errors": dict(errors),
            "gpu": gpu,
            "queue": rows["queue"],
            "storage_bytes": rows["storage"][0],
            "reserved_bytes": 2 * rows["storage"][1],
            "quota_bytes": self.storage.quota if self.storage else None,
        }


class Metrics:
    def __init__(self, service, scheduler, snapshot, *, allow_legacy=False):
        self.service, self.scheduler, self.snapshot = service, scheduler, snapshot
        self.registry = None
        try:
            from prometheus_client import CollectorRegistry, Counter as RequestCounter, Histogram, Gauge
        except ImportError:
            if not allow_legacy:
                raise ValueError("Install the cloud metrics dependency for this service") from None
            return
        self.registry = CollectorRegistry(auto_describe=False)
        self.requests = RequestCounter(
            "heteroes_http_requests_total",
            "Completed HTTP requests",
            ["service", "method", "route", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "heteroes_http_request_duration_seconds",
            "HTTP request duration",
            ["service", "method", "route", "status"],
            registry=self.registry,
        )
        Gauge("heteroes_service_up", "Process is serving requests", ["service"], registry=self.registry).labels(
            service
        ).set(1)
        if service == "scheduler":
            self.registry.register(self)

    def observe(self, method, route, status, seconds):
        if self.registry is not None:
            labels = (self.service, method, route, str(status))
            self.requests.labels(*labels).inc()
            self.duration.labels(*labels).observe(seconds)

    def render(self):
        if self.registry is None:
            return f'heteroes_service_up{{service="{self.service}"}} 1\n'.encode(), "text/plain; version=0.0.4"
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

        return generate_latest(self.registry), CONTENT_TYPE_LATEST

    def collect(self):
        from prometheus_client.core import GaugeMetricFamily

        data = self.scheduler.read_metrics(self.snapshot.capture)
        leader = GaugeMetricFamily(
            "heteroes_scheduler_leader", "This process holds live scheduler leadership", labels=["service"]
        )
        leader.add_metric([self.service], int(data is not None))
        yield leader
        if data is None:
            return

        def scalar(name, description, value):
            metric = GaugeMetricFamily(name, description, labels=["service"])
            metric.add_metric([self.service], value)
            return metric

        for name, description, field in (
            ("heteroes_devices_online", "Devices seen within thirty seconds", "online"),
            ("heteroes_queue_depth", "Rows in the product queue", "queue"),
            ("heteroes_generations_completed", "Completed generations in retained product runs", "generations"),
            (
                "heteroes_recovery_storage_bytes",
                "Committed recovery bytes tracked in the product database",
                "storage_bytes",
            ),
            (
                "heteroes_storage_reserved_bytes",
                "Reserved recovery bytes tracked in the product database",
                "reserved_bytes",
            ),
        ):
            yield scalar(name, description, data[field])
        if data["quota_bytes"] is not None:
            yield scalar("heteroes_storage_quota_bytes", "Configured recovery storage quota", data["quota_bytes"])
        for name, description, field, label in (
            ("heteroes_devices", "Registered devices by status", "devices", "status"),
            ("heteroes_runs", "Retained product runs by status", "runs", "status"),
            (
                "heteroes_candidate_attempt_errors",
                "Failed candidate attempts in retained snapshots",
                "errors",
                "error_type",
            ),
        ):
            metric = GaugeMetricFamily(name, description, labels=["service", label])
            for value, count in data[field].items():
                metric.add_metric([self.service, value], count)
            yield metric
        gpu_fields = (
            ("heteroes_gpu_utilization_percent", "utilizationPercent", 1, 100),
            ("heteroes_gpu_temperature_celsius", "temperatureC", 1, 200),
            ("heteroes_gpu_vram_used_bytes", "vramUsedMb", 1024**2, 1_000_000),
            ("heteroes_gpu_vram_total_bytes", "vramTotalMb", 1024**2, 1_000_000),
            ("heteroes_gpu_power_watts", "powerDrawW", 1, 10_000),
        )
        for name, field, factor, maximum in gpu_fields:
            metric = GaugeMetricFamily(
                name, "Latest reported GPU observation; unavailable values are omitted", labels=["service", "device_id"]
            )
            for device in data["gpu"]:
                value = _number(device["observation"].get(field), maximum)
                if value is not None:
                    metric.add_metric([self.service, device["device_id"]], value * factor)
            yield metric
        for name, field in (
            ("heteroes_device_online", "online"),
            ("heteroes_gpu_sample_timestamp_seconds", "sampled_at"),
        ):
            metric = GaugeMetricFamily(name, "Latest device observation and freshness", labels=["service", "device_id"])
            for device in data["gpu"]:
                if device[field] is not None:
                    metric.add_metric([self.service, device["device_id"]], device[field])
            yield metric


def emit_request(service, method, route, status, duration, request_id, *, failed=False):
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level": "ERROR" if failed or status >= 500 else "INFO",
        "service": service,
        "method": method,
        "route": route,
        "status": status,
        "duration_ms": duration * 1000,
        "request_id": request_id,
    }
    with _LOG_LOCK:
        sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
        sys.stdout.flush()
