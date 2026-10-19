import time
from datetime import datetime
import pytest
from heteroes.product.energy import EnergyLedger
from heteroes.product import power


def test_persistence_alias_dedup_and_boot_gap(tmp_path):
    a=EnergyLedger(tmp_path)
    a.record('gpu:one','boot',10,100,100)
    assert a.record('gpu:one','boot',20,110,100)['lifetimeWh']==pytest.approx(1000/3600)
    b=EnergyLedger(tmp_path)
    row=b.record('gpu:one','boot',20,110,100)
    assert row['sessionWh']==0 and row['lifetimeWh']==pytest.approx(1000/3600)
    b.record('gpu:one','boot',100,190,100)
    b.record('gpu:one','newboot',1,200,100)
    assert b.record('gpu:one','newboot',11,210,100)['lifetimeWh']==pytest.approx(2000/3600)


def test_missing_clock_jump_wrap_reset_and_midnight(tmp_path):
    ledger=EnergyLedger(tmp_path)
    midnight=datetime(2026,10,12).astimezone().timestamp()
    ledger.record('cpu','boot',1,midnight-5,900000,'counter',1000000)
    row=ledger.record('cpu','boot',11,midnight+5,100000,'counter',1000000)
    assert row['lifetimeWh']==pytest.approx(200000/3.6e9)
    assert row['todayWh']==pytest.approx(row['lifetimeWh']/2)
    ledger.record('cpu','boot',21,midnight+15,50000,'counter',1000000) # reset, not wrap
    ledger.record('cpu','boot',31,midnight+15,60000,'counter',1000000) # stopped wall clock
    assert ledger.summary('cpu',midnight+15)['lifetimeWh']==row['lifetimeWh']
    ledger.record('cpu','boot',32,midnight+16,None)
    ledger.record('cpu','boot',33,midnight+17,100000,'counter',1000000)
    assert ledger.summary('cpu',midnight+17)['lifetimeWh']==row['lifetimeWh']


def test_package_subdomain_not_double_counted_and_no_invented_wall(tmp_path,monkeypatch):
    readings={'domains':[{'id':'intel-rapl:0','name':'package-0','energyUj':1000000,'maxEnergyUj':100000000},
                         {'id':'intel-rapl:0:0','name':'core','energyUj':1000000,'maxEnergyUj':100000000}], 'tick':10,'sampledAt':100}
    monkeypatch.setattr(power,'rapl_observation',lambda:readings)
    monkeypatch.setattr(power.Path,'home',lambda:tmp_path)
    sampler=power.PowerSampler(tmp_path)
    gpu={'uuid':'GPU-one','name':'GPU','powerDrawW':20}
    sampler.sample(gpu,100,10)
    readings.update(tick=12,sampledAt=102)
    readings['domains'][0]['energyUj']+=20000000
    readings['domains'][1]['energyUj']+=10000000
    row=sampler.sample(gpu,102,12)
    assert row['componentSubtotalW']==30 # 10 package + 20 GPU, excludes nested core 5 W
    assert row['wholeMachineW'] is None
    assert row['wholeMachineUnavailableReason']=='NO_WHOLE_MACHINE_METER'
    assert row['components'][1]['includedInSubtotal'] is False


def test_legacy_wire_keeps_detail_private(tmp_path):
    from heteroes.product.telemetry import legacy_observation
    source={'host':{'platform':'linux','cpuPercent':2,'processes':[{'pid':1}]},'gpu':{'uuid':'GPU-one','processes':[]},'power':{'hostId':'private'}}
    assert legacy_observation(source)=={'host':{'platform':'linux','cpuPercent':2},'gpu':{'uuid':'GPU-one'}}
    assert 'power' in source and source['host']['processes']


def test_wall_meter_requires_matching_host_scope_and_fresh_timestamp(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(power.Path,'home',lambda:tmp_path)
    monkeypatch.setattr(power,'rapl_observation',lambda:{'domains':[]})
    sampler=power.PowerSampler(tmp_path/'data')
    meter=tmp_path/'.config/heteroes-power/wall-meter.json';meter.parent.mkdir(parents=True)
    for change in ({'hostId':'wrong'},{'scope':'gpu'},{'sampledAt':50},{'watts':-1}):
        row={'hostId':sampler.host,'scope':'whole-machine-ac','sampledAt':100,'watts':150,'source':'test meter'};row.update(change)
        meter.write_text(json.dumps(row))
        assert sampler.sample(None,100,10)['wholeMachineW'] is None
    meter.write_text(json.dumps({'hostId':sampler.host,'scope':'whole-machine-ac','sampledAt':100,'watts':150,'source':'test meter'}))
    assert sampler.sample(None,100,10)['wholeMachineW']==150
    meter.write_text(json.dumps({'hostId':sampler.host,'scope':'whole-machine-ac','sampledAt':110,'watts':150,'source':'test meter'}))
    row=sampler.sample(None,110,20)
    assert row['components'][-1]['energy']['lifetimeWh']==pytest.approx(1500/3600)
    assert row['componentSubtotalW'] is None # Wall is not added to component subtotal.


def test_host_process_privacy_and_pid_reuse(tmp_path,monkeypatch):
    from heteroes.product.host_detail import HostDetail
    proc=tmp_path/'proc';sys=tmp_path/'sys';proc.mkdir();sys.mkdir()
    for file,data in {'uptime':'100 0','cpuinfo':'model name : Test CPU','stat':'cpu0 10 0 0 90 0 0 0 0','meminfo':'MemAvailable: 100 kB\n','net/dev':'a\nb\n','diskstats':''}.items():
        path=proc/file;path.parent.mkdir(exist_ok=True,parents=True);path.write_text(data)
    process=proc/'123';process.mkdir();(process/'cmdline').write_text('password=SECRET');(process/'environ').write_text('TOKEN=SECRET')
    def stats(start,cpu):
        fields=['0']*22;fields[0]='S';fields[11]=str(cpu);fields[17]='2';fields[19]=str(start);fields[21]='3'
        (process/'stat').write_text('123 (process with ) paren) '+' '.join(fields))
    tick=[10];monkeypatch.setattr(time,'monotonic',lambda:tick[0]);stats(100,100)
    sampler=HostDetail(proc,sys);sampler.sample();tick[0]=12;stats(100,200)
    row=sampler.sample()['processes'][0]
    assert row['name']=='process with ) paren' and row['cpuPercent'] is not None
    assert 'SECRET' not in str(row)
    tick[0]=14;stats(200,10)
    assert sampler.sample()['processes'][0]['cpuPercent'] is None


def test_short_cpu_sensor_outage_breaks_energy_interval_and_retains_totals(tmp_path,monkeypatch):
    monkeypatch.setattr(power.Path,'home',lambda:tmp_path)
    domain={'id':'intel-rapl:0','name':'package-0','energyUj':1000000,'maxEnergyUj':100000000}
    reading={'domains':[domain],'tick':10,'sampledAt':100}
    monkeypatch.setattr(power,'rapl_observation',lambda:reading)
    sampler=power.PowerSampler(tmp_path/'data');sampler.sample(None,100,10)
    domain['energyUj']+=20000000;reading.update(tick=12,sampledAt=102)
    observed=sampler.sample(None,102,12)['components'][0]['energy']['lifetimeWh']
    reading.update(domains=[],tick=14,sampledAt=104)
    missing=sampler.sample(None,104,14)['components'][0]
    assert missing['powerW'] is None and missing['energy']['lifetimeWh']==observed
    domain['energyUj']+=20000000;reading.update(domains=[domain],tick=16,sampledAt=106)
    recovered=sampler.sample(None,106,16)['components'][0]
    assert recovered['powerW'] is None and recovered['energy']['lifetimeWh']==observed
