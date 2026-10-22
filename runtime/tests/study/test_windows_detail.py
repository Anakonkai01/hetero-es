from heteroes.product.windows_detail import WindowsDetail, SCRIPT


def sample():
    return {
        "os": [{"TotalVisibleMemorySize": 1000, "FreePhysicalMemory": 250}],
        "cores": [{"Name": "_Total", "PercentProcessorTime": 40}, {"Name": "0", "PercentProcessorTime": 50}],
        "network": [{"Name": "Ethernet", "ReceivedBytes": 100, "SentBytes": 200}],
        "disk": [
            {"Name": "0 C:", "DiskReadBytesPerSec": 1000, "DiskWriteBytesPerSec": 2000, "CurrentDiskQueueLength": 1}
        ],
        "process": [
            {
                "Name": "python",
                "IDProcess": 42,
                "WorkingSet": 999,
                "ThreadCount": 2,
                "PercentProcessorTime": 120,
                "CommandLine": "secret",
            }
        ],
        "thermal": [{"InstanceName": "zone", "CurrentTemperature": 3000}],
    }


def test_windows_real_counters_rates_missing_sensors_and_process_privacy():
    times = iter([1, 3, 5])
    collector = WindowsDetail(clock=lambda: next(times))
    a = collector.normalize(sample())
    assert a["ramUsedBytes"] == 750 * 1024
    assert "clockMhz" not in a["cores"][0]
    assert "CommandLine" not in str(a) and "secret" not in str(a)
    b = sample()
    b["network"][0]["ReceivedBytes"] = 200
    result = collector.normalize(b)
    assert result["networkInterfaces"][0]["rxBytesPerSecond"] == 50
    result = collector.normalize(sample())
    assert "rxBytesPerSecond" not in result["networkInterfaces"][0]
    assert "CommandLine" not in SCRIPT and "Environment" not in SCRIPT


def test_unavailable_windows_counters_are_empty_not_fabricated_zero():
    result = WindowsDetail().normalize({})
    assert result["sensors"] == [] and "cpuPercent" not in result and "ramTotalBytes" not in result


def test_windows_host_totals_sum_all_adapters_and_disks_after_warmup():
    ticks = iter([1, 3, 5])
    collector = WindowsDetail(clock=lambda: next(ticks))
    first = sample()
    first["network"].append({"Name": "Wi-Fi", "ReceivedBytes": 1000, "SentBytes": 2000})
    assert "networkRxBytesPerSecond" not in collector.normalize(first)
    second = sample()
    second["network"][0].update(ReceivedBytes=200, SentBytes=300)
    second["network"].append({"Name": "Wi-Fi", "ReceivedBytes": 1400, "SentBytes": 2600})
    second["disk"][0].update(DiskReadBytesPerSec=1200, DiskWriteBytesPerSec=2400)
    result = collector.normalize(second)
    assert result["networkRxBytesPerSecond"] == 250 and result["networkTxBytesPerSecond"] == 350
    assert result["diskReadBytesPerSecond"] == 100 and result["diskWriteBytesPerSecond"] == 200
    third = collector.normalize(second)
    assert third["networkRxBytesPerSecond"] == 0 and third["diskWriteBytesPerSecond"] == 0
