import pytest
from heteroes.product import telemetry


def gpu(watts=100):
    return {"uuid": "GPU-test", "name": "test GPU", "powerDrawW": watts}


def test_legacy_wire_strips_new_availability_metadata():
    row = {"host": {"platform": "linux"}, "availability": {"cpuPercent": {"status": "warming_up"}}}
    assert "availability" not in telemetry.legacy_observation(row)


def test_missing_metrics_have_evidence_based_status_without_replacing_zero(tmp_path, monkeypatch):
    sampler = telemetry.TelemetrySampler(tmp_path)
    monkeypatch.setattr(
        sampler, "host", lambda: {"platform": "windows", "cpuPercent": 0, "networkInterfaces": [{"name": "Ethernet"}]}
    )
    monkeypatch.setattr(telemetry, "gpu_observation", lambda _: None)
    row = sampler.sample()
    assert row["host"]["cpuPercent"] == 0 and "cpuPercent" not in row["availability"]
    assert row["availability"]["networkRxBytesPerSecond"]["status"] == "warming_up"
    assert row["availability"]["cpuPowerW"]["status"] == "unsupported"
    assert row["availability"]["gpuUtilizationPercent"]["status"] == "error"


def test_energy_integrates_only_observed_short_intervals(tmp_path, monkeypatch):
    tick = [0.0]
    monkeypatch.setattr(telemetry.time, "monotonic", lambda: tick[0])
    monkeypatch.setattr(telemetry, "gpu_observation", lambda _: gpu())
    sampler = telemetry.TelemetrySampler(tmp_path)
    monkeypatch.setattr(sampler, "host", lambda: {"platform": "linux"})
    assert sampler.sample()["gpu"]["energyWh"] is None
    tick[0] = 10
    assert sampler.sample()["gpu"]["energyWh"] == pytest.approx(100 * 10 / 3600)
    tick[0] = 100  # A long outage does not extrapolate unobserved power.
    row = sampler.sample()["gpu"]
    assert row["energyWh"] == pytest.approx(100 * 10 / 3600)
    assert row["energySampledSeconds"] == 10


def test_missing_gpu_does_not_hide_host_or_disk_data(tmp_path, monkeypatch):
    def unavailable(_):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(telemetry, "gpu_observation", unavailable)
    sampler = telemetry.TelemetrySampler(tmp_path, tmp_path / "missing-volume")
    monkeypatch.setattr(sampler, "host", lambda: {"platform": "linux", "ramUsedBytes": 1234})
    row = sampler.sample()
    assert row["host"]["ramUsedBytes"] == 1234
    assert "gpu" not in row
    assert row["disks"][0]["label"] == "state"
    assert "DISK_METRICS_UNAVAILABLE" in row["errors"]
    assert not (tmp_path / "missing-volume").exists()


def test_gpu_selects_qualified_uuid_and_marks_unsupported_fields(monkeypatch):
    class Response:
        stdout = "GPU-other,Other GPU,0,30,8192,0,10,200,0,300\nGPU-selected,Selected GPU,50,60,16384,4096,120,N/A,[Not Supported],1500\n"

    monkeypatch.setattr(telemetry.subprocess, "run", lambda *a, **kw: Response())
    row = telemetry.gpu_observation("GPU-selected")
    assert row["name"] == "Selected GPU"
    assert row["powerDrawW"] == 120
    assert row["fanPercent"] is None and row["powerLimitW"] is None
    assert telemetry.gpu_observation("GPU-missing") is None


def test_host_permission_failure_is_distinct_from_unsupported_or_zero(tmp_path, monkeypatch):
    sampler = telemetry.TelemetrySampler(tmp_path)

    def denied():
        raise PermissionError("host metrics")

    monkeypatch.setattr(sampler, "host", denied)
    monkeypatch.setattr(telemetry, "gpu_observation", lambda _: None)
    row = sampler.sample()
    assert row["availability"]["cpuPercent"]["status"] == "permission_denied"
