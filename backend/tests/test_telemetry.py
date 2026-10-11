import time
import uuid
from test_devices import lab,pair,boot


def observation(alias='test-gpu'):
    return {'sampledAt':time.time(),'sessionStartedAt':time.time()-10,'source':'host-observation',
            'host':{'platform':'linux','cpuPercent':25,'ramTotalBytes':1000,'ramUsedBytes':500},
            'gpu':{'uuid':'GPU-'+str(uuid.uuid5(uuid.NAMESPACE_DNS,alias)),'name':'GPU',
                   'vramTotalMb':12000,'vramUsedMb':1000,'powerDrawW':55,'utilizationPercent':50,
                   'temperatureC':42,'energyWh':0.2,'energySampledSeconds':10},
            'disks':[{'label':'state','totalBytes':1000,'usedBytes':200,'freeBytes':800}]}


def test_telemetry_round_trip_and_boot_reset_preserve_contribution(lab):
    c,s,r,admin=lab;d,auth=pair(lab)
    response=boot(c,auth,'boot-1',telemetry=observation())
    assert response['telemetrySupported']
    rows=c.get('/api/v1/workers',headers=admin).json()
    w=next(w for w in rows if w['workerId']=='test-gpu')
    assert w['telemetry']['gpu']['powerDrawW']==55
    assert w['telemetry']['receivedAt']>0
    assert w['profile']['vramFreeMb']==11000
    assert w['temperatureC']==42
    assert w['telemetryHistory'][0]['gpuPowerW']==55
    boot(c,auth,'boot-1',telemetry=observation())
    assert len(r.workers()[0]['telemetryHistory'])==2
    assert not w['contributionEnabled']
    boot(c,auth,'boot-2')
    assert r.workers()[0]['telemetry'] is None
    assert not r.workers()[0]['contributionEnabled']


def test_telemetry_rejects_wrong_gpu_and_invalid_measurements(lab):
    c,_,r,_=lab;d,auth=pair(lab)
    for change in [{'uuid':'GPU-other'},{'powerDrawW':-1},{'temperatureC':999}, {'utilizationPercent':101}]:
        row=observation();row['gpu'].update(change)
        response=c.post('/api/v1/device/poll',headers=auth,json={'bootId':'boot-1','telemetry':row})
        assert response.status_code==422
    assert r.workers()[0]['telemetry'] is None


def test_history_is_bounded_and_identical_samples_are_deduplicated(lab):
    c,_,r,_=lab;d,auth=pair(lab)
    row=observation()
    boot(c,auth,'boot-1',telemetry=row)
    boot(c,auth,'boot-1',telemetry=row)
    assert len(r.workers()[0]['telemetryHistory'])==1
    for i in range(185):
        row['sampledAt']+=1
        boot(c,auth,'boot-1',telemetry=row)
    with r.store.db() as db:
        assert db.execute('select count(*) from device_telemetry_history where device_id=?',(d['deviceId'],)).fetchone()[0]==180
    assert len(r.workers()[0]['telemetryHistory'])==60
