"""Best-effort host/GPU observations; never import torch or start a CUDA context."""
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def gpu_observation(uuid=None):
    fields = 'uuid,name,utilization.gpu,temperature.gpu,memory.total,memory.used,power.draw,power.limit,fan.speed,clocks.current.graphics'
    result = subprocess.run(['nvidia-smi', '--query-gpu=' + fields, '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, timeout=3, check=True)
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 10 or (uuid and parts[0] != uuid):
            continue
        keys = ['utilizationPercent', 'temperatureC', 'vramTotalMb', 'vramUsedMb',
                'powerDrawW', 'powerLimitW', 'fanPercent', 'clockMhz']
        return {'uuid': parts[0], 'name': parts[1], **dict(zip(keys, map(number, parts[2:]))) }
    return None


class TelemetrySampler:
    def __init__(self, state_directory, storage_directory=None, gpu_uuid=None):
        self.state_directory = Path(state_directory)
        self.storage_directory = Path(storage_directory) if storage_directory else None
        self.gpu_uuid = gpu_uuid
        self.cpu_previous = None
        self.io_previous = None
        self.energy_previous = None
        self.energy_wh = 0.0
        self.sampled_seconds = 0.0
        self.started_at = time.time()
        from collections import deque
        self.history = deque(maxlen=60)
        self.last = None
        self.last_tick = None

    def host(self):
        result = {'cpuCount': os.cpu_count(), 'platform': platform.system().lower()}
        if platform.system() == 'Linux':
            values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
            total, idle = sum(values), values[3] + values[4]
            if self.cpu_previous:
                dt, di = total - self.cpu_previous[0], idle - self.cpu_previous[1]
                if dt > 0:
                    result['cpuPercent'] = max(0, min(100, 100 * (dt - di) / dt))
            self.cpu_previous = total, idle
            memory = {line.split(':')[0]: int(line.split()[1]) * 1024
                      for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) >= 2}
            result.update(ramTotalBytes=memory['MemTotal'],
                          ramUsedBytes=memory['MemTotal'] - memory.get('MemAvailable', memory.get('MemFree', 0)),
                          swapTotalBytes=memory.get('SwapTotal'),
                          swapUsedBytes=memory.get('SwapTotal', 0) - memory.get('SwapFree', 0))
            result['loadAverage'] = list(os.getloadavg())
            rx = tx = read = written = 0
            for line in Path('/proc/net/dev').read_text().splitlines()[2:]:
                name, data = line.split(':', 1)
                if name.strip() == 'lo': continue
                parts = data.split(); rx += int(parts[0]); tx += int(parts[8])
            import re
            for line in Path('/proc/diskstats').read_text().splitlines():
                parts = line.split()
                if len(parts) >= 10 and re.fullmatch(r'(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+)', parts[2]):
                    read += int(parts[5]) * 512; written += int(parts[9]) * 512
            tick = time.monotonic(); counters = [rx, tx, read, written]
            if self.io_previous:
                before, old = self.io_previous
                if tick > before:
                    for key, current, previous in zip(['networkRxBytesPerSecond','networkTxBytesPerSecond',
                                                      'diskReadBytesPerSecond','diskWriteBytesPerSecond'], counters, old):
                        if current >= previous: result[key] = (current - previous) / (tick - before)
            self.io_previous = tick, counters
        elif platform.system() == 'Windows':
            # Fixed query, no caller-supplied command text. Works without psutil.
            script = "$o=Get-CimInstance Win32_OperatingSystem;$c=Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter \"Name='_Total'\";@{cpuPercent=$c.PercentProcessorTime;ramTotalBytes=([double]$o.TotalVisibleMemorySize*1024);ramUsedBytes=([double]($o.TotalVisibleMemorySize-$o.FreePhysicalMemory)*1024)}|ConvertTo-Json -Compress"
            response = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                      capture_output=True, text=True, timeout=4, check=True,
                                      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result.update(json.loads(response.stdout))
        return result

    def sample(self):
        now, tick = time.time(), time.monotonic()
        if self.last_tick is not None and tick - self.last_tick < 10:
            return self.last
        row = {'sampledAt': now, 'sessionStartedAt': self.started_at, 'source': 'host-observation', 'disks': []}
        errors = []
        try:
            row['host'] = self.host()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            errors.append('HOST_METRICS_UNAVAILABLE')
        try:
            gpu = gpu_observation(self.gpu_uuid)
            if gpu:
                watts = gpu['powerDrawW']
                if self.energy_previous and watts is not None:
                    before, previous_watts = self.energy_previous
                    dt = tick - before
                    if 0 < dt <= 30:
                        self.energy_wh += (previous_watts + watts) * 0.5 * dt / 3600
                        self.sampled_seconds += dt
                self.energy_previous = (tick, watts) if watts is not None else None
                gpu.update(energyWh=self.energy_wh if self.sampled_seconds else None,
                           energySampledSeconds=self.sampled_seconds)
                row['gpu'] = gpu
            else:
                self.energy_previous = None
                errors.append('GPU_METRICS_UNAVAILABLE')
        except (OSError, subprocess.SubprocessError):
            self.energy_previous = None
            errors.append('GPU_METRICS_UNAVAILABLE')
        for label, directory in [('state', self.state_directory), ('artifacts', self.storage_directory)]:
            if directory is None:
                continue
            # Never create a missing external mount as a side effect of monitoring.
            try:
                usage = shutil.disk_usage(directory)
                row['disks'].append({'label': label, 'totalBytes': usage.total,
                                     'usedBytes': usage.used, 'freeBytes': usage.free})
            except OSError:
                errors.append('DISK_METRICS_UNAVAILABLE')
        row['errors'] = errors
        gpu, host = row.get('gpu', {}), row.get('host', {})
        self.history.append({'at': now, 'gpuPowerW': gpu.get('powerDrawW'),
                             'temperatureC': gpu.get('temperatureC'), 'gpuPercent': gpu.get('utilizationPercent'),
                             'cpuPercent': host.get('cpuPercent'), 'vramUsedMb': gpu.get('vramUsedMb'),
                             'ramUsedBytes': host.get('ramUsedBytes')})
        self.last, self.last_tick = row, tick
        return row
