import time
import uuid
from labkit import boot, pair


def observation(alias="test-gpu"):
    return {
        "sampledAt": time.time(),
        "sessionStartedAt": time.time() - 10,
        "source": "host-observation",
        "host": {"platform": "linux", "cpuPercent": 25, "ramTotalBytes": 1000, "ramUsedBytes": 500},
        "gpu": {
            "uuid": "GPU-" + str(uuid.uuid5(uuid.NAMESPACE_DNS, alias)),
            "name": "GPU",
            "vramTotalMb": 12000,
            "vramUsedMb": 1000,
            "powerDrawW": 55,
            "utilizationPercent": 50,
            "temperatureC": 42,
            "energyWh": 0.2,
            "energySampledSeconds": 10,
        },
        "disks": [{"label": "state", "totalBytes": 1000, "usedBytes": 200, "freeBytes": 800}],
    }


def test_availability_metadata_negotiates_and_round_trips(lab):
    client, _, runtime, _ = lab
    _, auth = pair(lab)
    row = observation()
    row["availability"] = {"cpuTemperatureC": {"status": "unsupported"}}
    response = boot(client, auth, "boot-1", telemetry=row)
    assert response["metricAvailabilitySupported"] is True
    assert runtime.workers()[0]["telemetry"]["availability"] == row["availability"]


def test_telemetry_round_trip_and_boot_reset_preserve_contribution(lab):
    c, s, r, admin = lab
    d, auth = pair(lab)
    response = boot(c, auth, "boot-1", telemetry=observation())
    assert response["telemetrySupported"]
    rows = c.get("/api/v1/workers", headers=admin).json()
    w = next(w for w in rows if w["workerId"] == "test-gpu")
    assert w["telemetry"]["gpu"]["powerDrawW"] == 55
    assert w["telemetry"]["receivedAt"] > 0
    assert w["profile"]["vramFreeMb"] == 11000
    assert w["temperatureC"] == 42
    assert w["telemetryHistory"][0]["gpuPowerW"] == 55
    boot(c, auth, "boot-1", telemetry=observation())
    assert len(r.workers()[0]["telemetryHistory"]) == 2
    assert not w["contributionEnabled"]
    boot(c, auth, "boot-2")
    assert r.workers()[0]["telemetry"] is None
    assert not r.workers()[0]["contributionEnabled"]


def test_telemetry_rejects_wrong_gpu_and_invalid_measurements(lab):
    c, _, r, _ = lab
    d, auth = pair(lab)
    for change in [{"uuid": "GPU-other"}, {"powerDrawW": -1}, {"temperatureC": 999}, {"utilizationPercent": 101}]:
        row = observation()
        row["gpu"].update(change)
        response = c.post("/api/v1/device/poll", headers=auth, json={"bootId": "boot-1", "telemetry": row})
        assert response.status_code == 422
    assert r.workers()[0]["telemetry"] is None


def test_history_is_bounded_and_identical_samples_are_deduplicated(lab):
    c, _, r, _ = lab
    d, auth = pair(lab)
    row = observation()
    boot(c, auth, "boot-1", telemetry=row)
    boot(c, auth, "boot-1", telemetry=row)
    assert len(r.workers()[0]["telemetryHistory"]) == 1
    for i in range(185):
        row["sampledAt"] += 1
        boot(c, auth, "boot-1", telemetry=row)
    with r.store.db() as db:
        assert (
            db.execute("select count(*) from device_telemetry_history where device_id=?", (d["deviceId"],)).fetchone()[
                0
            ]
            == 180
        )
    assert len(r.workers()[0]["telemetryHistory"]) == 60


def test_detail_round_trip_bounds_and_power_history(lab):
    c, _, r, admin = lab
    _, auth = pair(lab)
    row = observation()
    energy = dict(
        sessionWh=0.1,
        todayWh=0.2,
        monthWh=0.2,
        lifetimeWh=0.2,
        sessionSampledSeconds=10,
        sampledSeconds=20,
        todaySampledSeconds=20,
        monthSampledSeconds=20,
        since=time.time() - 20,
        day="2026-10-11",
        month="2026-10",
        timezone="ICT",
    )
    row["host"].update(
        cores=[{"id": "cpu0", "utilizationPercent": 50}],
        processes=[{"pid": 1, "name": "python", "state": "S", "cpuPercent": 125, "ramBytes": 1024, "threads": 3}],
        sensors=[
            {
                "id": "hwmon0/temp1",
                "group": "coretemp",
                "label": "Package id 0",
                "kind": "temperature",
                "value": 42,
                "unit": "°C",
            }
        ],
    )
    row["power"] = {
        "hostId": "a" * 32,
        "components": [
            {
                "id": "cpu:host:package0",
                "label": "package-0",
                "kind": "cpu-package",
                "powerW": 20,
                "includedInSubtotal": True,
                "method": "rapl-counter",
                "energy": energy,
            }
        ],
        "componentSubtotalW": 75,
        "wholeMachineW": None,
        "wholeMachineUnavailableReason": "NO_WHOLE_MACHINE_METER",
    }
    assert boot(c, auth, "boot-1", telemetry=row)["detailedTelemetrySupported"]
    worker = r.workers()[0]
    assert worker["telemetry"]["host"]["processes"][0]["cpuPercent"] == 125
    assert worker["telemetry"]["power"]["components"][0]["energy"]["lifetimeWh"] == 0.2
    assert worker["telemetryHistory"][-1]["cpuPowerW"] == 20
    assert not worker["contributionEnabled"]
    row["host"]["processes"][0]["arguments"] = "secret"
    assert c.post("/api/v1/device/poll", headers=auth, json={"bootId": "boot-1", "telemetry": row}).status_code == 422
    del row["host"]["processes"][0]["arguments"]
    row["host"]["cores"] *= 513
    assert c.post("/api/v1/device/poll", headers=auth, json={"bootId": "boot-1", "telemetry": row}).status_code == 422
