"""Hardware counter readers and an optional local whole-machine meter input."""
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import time
from .energy import EnergyLedger


def machine_identity():
    try:
        if platform.system() == 'Windows':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography') as key:
                raw = winreg.QueryValueEx(key, 'MachineGuid')[0]
        else:
            raw = Path('/etc/machine-id').read_text().strip()
    except OSError:
        raw = socket.gethostname()
    return hashlib.sha256(('heteroes-host-v1:' + raw).encode()).hexdigest()[:32]


def boot_identity():
    try:
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    except OSError:
        if platform.system() == 'Windows':
            import ctypes
            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            return str(round((time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000) / 60))
        return 'unknown-boot'


def rapl_observation():
    try:
        row = json.loads(Path('/run/heteroes-power/rapl.json').read_text())
        if row['bootId'] == boot_identity() and 0 <= time.time() - row['sampledAt'] <= 8:
            return row
    except (OSError, ValueError, KeyError):
        pass
    domains = []
    for path in sorted(Path('/sys/class/powercap').glob('intel-rapl:*'))[:64]:
        try:
            domains.append({'id': path.name, 'name': (path / 'name').read_text().strip(),
                            'energyUj': int((path / 'energy_uj').read_text()),
                            'maxEnergyUj': int((path / 'max_energy_range_uj').read_text())})
        except (OSError, ValueError):
            continue
    return {'bootId': boot_identity(), 'sampledAt': time.time(), 'tick': time.monotonic(), 'domains': domains}


class PowerSampler:
    def __init__(self, directory, gpu_uuid=None):
        self.host = machine_identity()
        self.boot = boot_identity()
        self.ledger = EnergyLedger(directory)
        self.previous = {}
        self.known_domains = {}
        self.gpu_uuid = gpu_uuid

    def sample(self, gpu, at, tick):
        components = []
        counters = rapl_observation() if platform.system() == 'Linux' else {'domains': []}
        active = {'cpu:' + self.host + ':' + d['id'] for d in counters['domains']}
        self.ledger.break_missing('cpu:' + self.host + ':', active)
        for domain in counters['domains']:
            identity = 'cpu:' + self.host + ':' + domain['id']; old = self.previous.get(identity)
            watts = None
            if old:
                dt = counters['tick'] - old[0]; delta = domain['energyUj'] - old[1]
                if delta < 0 and old[1] > domain['maxEnergyUj'] * .75 and domain['energyUj'] < domain['maxEnergyUj'] * .25:
                    delta += domain['maxEnergyUj']
                if 0 < dt <= 30 and delta >= 0:
                    watts = delta / 1_000_000 / dt
            self.previous[identity] = counters['tick'], domain['energyUj']
            name = domain['name']; kind = 'cpu-package' if name.startswith('package-') else 'dram' if name == 'dram' else 'cpu-domain'
            self.known_domains[identity] = name, kind
            components.append({'id': identity, 'label': name, 'kind': kind, 'powerW': watts,
                               'includedInSubtotal': kind in ('cpu-package', 'dram'), 'method': 'rapl-counter',
                               'energy': self.ledger.record(identity, self.boot, counters['tick'], counters['sampledAt'],
                                                            domain['energyUj'], 'counter', domain['maxEnergyUj'])})
        for identity, (name, kind) in self.known_domains.items():
            if identity not in active:
                self.previous.pop(identity, None)
                components.append({'id': identity, 'label': name, 'kind': kind, 'powerW': None,
                                   'includedInSubtotal': kind in ('cpu-package', 'dram'), 'method': 'unavailable',
                                   'energy': self.ledger.summary(identity, at)})
        if not any(row['kind'] == 'cpu-package' for row in components):
            components.append({'id': 'cpu:' + self.host, 'label': 'CPU package', 'kind': 'cpu-package',
                               'powerW': None, 'includedInSubtotal': True, 'method': 'unavailable',
                               'energy': self.ledger.summary('cpu:' + self.host, at)})
        if gpu or self.gpu_uuid:
            if gpu: self.gpu_uuid = gpu['uuid']
            identity = 'gpu:' + self.gpu_uuid
            components.append({'id': identity, 'label': gpu['name'] if gpu else 'GPU', 'kind': 'gpu', 'powerW': gpu.get('powerDrawW') if gpu else None,
                               'includedInSubtotal': True, 'method': 'sampled-gpu' if gpu else 'unavailable',
                               'energy': self.ledger.record(identity, self.boot, tick, at, gpu.get('powerDrawW') if gpu else None)})
        # Fixed local input supplied by a meter bridge; never fetch caller-provided URLs.
        wall, source = None, None
        try:
            meter = json.loads((Path.home() / '.config/heteroes-power/wall-meter.json').read_text())
            if meter['hostId'] == self.host and meter['scope'] == 'whole-machine-ac' and 0 <= at - meter['sampledAt'] <= 15:
                candidate = float(meter['watts'])
                if 0 <= candidate <= 100_000:
                    wall, source = candidate, str(meter['source'])[:100]
        except (OSError, KeyError, ValueError, TypeError):
            pass
        identity = 'wall:' + self.host
        components.append({'id': identity, 'label': source or 'Whole machine', 'kind': 'wall', 'powerW': wall,
                           'includedInSubtotal': False, 'method': 'external-meter' if wall is not None else 'unavailable',
                           'energy': self.ledger.record(identity, self.boot, tick, at, wall)})
        included = [row['powerW'] for row in components if row['includedInSubtotal'] and row['powerW'] is not None]
        return {'hostId': self.host, 'components': components,
                'componentSubtotalW': sum(included) if included else None, 'wholeMachineW': wall,
                'wholeMachineSource': source, 'wholeMachineUnavailableReason': None if wall is not None else 'NO_WHOLE_MACHINE_METER',
                'cpuUnavailableReason': None if counters['domains'] else 'CPU_POWER_SENSOR_UNAVAILABLE'}
