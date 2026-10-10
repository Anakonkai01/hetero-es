"""CPU-only protocol contracts; no runtime or CUDA import is allowed here."""
import json
import time
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.devices import AgentRuntime
from test_api import login, draft


@pytest.fixture
def lab(tmp_path):
    runtime = AgentRuntime()
    app = create_app(tmp_path/'lab.sqlite', {'admin':'test-admin-pass'}, runtime, dispatch=False)
    with TestClient(app) as client:
        yield client, app.state.store, runtime, login(client, 'admin')


def pair(lab, alias='test-gpu', coordinator=True):
    client, store, runtime, admin = lab
    code = client.post('/api/v1/devices/pairing-codes',headers=admin).json()['code']
    data = {'code':code,'workerId':alias,'displayName':alias,
            'selfTest':{'passed':True,'coordinator':coordinator,'gpuName':'Fake CPU test GPU',
                        'vramTotalMb':12000,'noiseVersion':'numpy_pcg64_normal_f32_to_f16_v1'},
            'computeUrl':'http://100.64.0.1:8769'}
    response = client.post('/api/v1/device/enroll',json=data)
    assert response.status_code == 201, response.text
    d=response.json()
    auth={'Authorization':'Bearer '+d['deviceToken']}
    assert client.post('/api/v1/device/enroll',json=data).status_code == 409
    assert client.patch('/api/v1/platform/devices/'+d['deviceId'],json={'approved':True,'workspaceId':'lab'},headers=admin).status_code == 200
    boot(client,auth,'boot-1')
    return d, auth


def boot(client,auth,boot_id,**changes):
    data={'bootId':boot_id,'contribution':False,'processes':[], 'reports':[],**changes}
    response=client.post('/api/v1/device/poll',headers=auth,json=data)
    assert response.status_code == 200,response.text
    return response.json()


def enable(lab,d,auth,boot_id='boot-1'):
    client,_,_,admin=lab
    r=client.post('/api/v1/devices/'+d['deviceId']+'/contribution',headers=admin,json={'enabled':True,'bootId':boot_id})
    assert r.status_code==200,r.text
    return boot(client,auth,boot_id,contribution=True)


def queued(lab,d,**changes):
    client,store,_,admin=lab
    r=draft(client,admin,**{'workerIds':[d['workerId']],'coordinatorDeviceId':d['deviceId'],**changes})
    assert r.status_code==200,r.text
    rid=r.json()['experimentId']
    assert client.post(f'/api/v1/experiments/{rid}/submit',headers=admin).status_code==200
    return rid


def test_offline_queue_and_boot_activation_are_independent(lab):
    c,s,r,a=lab;d,h=pair(lab)
    rid=queued(lab,d)
    s.dispatch_once()
    assert s.get(rid)['status']=='QUEUED'
    assert r.runs()==[]
    enable(lab,d,h)
    s.dispatch_once()
    assert s.get(rid)['status']=='STARTING'
    assert len(r.runs())==1
    boot(c,h,'boot-2')
    assert c.post('/api/v1/devices/'+d['deviceId']+'/contribution',headers=a,json={'enabled':True,'bootId':'boot-1'}).status_code==409
    assert not r.devices()[0]['contributionEnabled']


def test_assignment_is_idempotent_and_outage_never_releases(lab):
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h)
    first,second=queued(lab,d),queued(lab,d,name='Second run')
    s.dispatch_once();s.dispatch_once()
    assignment=r.runs()[0]
    with s.db() as db:db.execute('UPDATE devices SET seen=0')
    s.dispatch_once()
    assert s.get(second)['status']=='QUEUED'
    assert r.runs()[0]['assignmentId']==assignment['assignmentId']
    assert len(r.reservations())==1
    assert len([x for x in r.commands(d['deviceId']) if x['kind']=='COORDINATE'])==1


def test_terminal_snapshot_needs_all_process_death_and_fresh_epoch(lab):
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h);rid=queued(lab,d);s.dispatch_once()
    assignment=r.runs()[0]
    report={'sequence':1,'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],
            'snapshot':{'state':{'status':'COMPLETED'},'generations':[],'candidates':[],
                        'attempts':[],'events':[],'artifacts':[],
                        'completedGenerationCount':3,'monitoringPartial':True,
                        'latestGeneration':{'generationId':'g2','committedCandidateCount':8,'modelVersion':'final'}}}
    boot(c,h,'boot-1',contribution=True,reports=[{**report,'epoch':99}])
    assert r.snapshot(rid)['state']['status']=='STARTING'
    boot(c,h,'boot-1',contribution=True,reports=[report])
    s.dispatch_once()
    assert s.get(rid)['status']=='DRAINING'
    assert r.reservations()
    boot(c,h,'boot-1',contribution=True,processes=[{'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],'coordinatorAlive':False,'workerAlive':False}],reports=[report])
    s.dispatch_once()
    assert s.get(rid)['status']=='COMPLETED'
    assert s.get(rid)['completedGenerations']==3
    assert s.get(rid)['currentGenerationId']=='g2'
    assert not r.reservations()
    enriched={**report,'sequence':2,'snapshot':{**report['snapshot'],'state':{'status':'FAILED'},
        'artifactContents':{'config.json':{'base64':'e30=','sha256':'unused'}}}}
    boot(c,h,'boot-1',reports=[enriched])
    assert s.get(rid)['status']=='COMPLETED'
    assert s.snapshot(rid)['state']['status']=='COMPLETED'
    assert 'config.json' in s.snapshot(rid)['artifactContents']


def test_pairing_expiry_alias_collision_and_revocation(lab):
    c,s,r,a=lab;d,h=pair(lab)
    assert c.post('/api/v1/device/poll',json={'bootId':'x'}).status_code==401
    assert c.patch('/api/v1/platform/devices/'+d['deviceId'],headers=a,json={'approved':False,'workspaceId':'lab'}).status_code==200
    drained=c.post('/api/v1/device/poll',headers=h,json={'bootId':'x'})
    assert drained.status_code==200 and not drained.json()['desiredContribution']
    assert c.post('/api/v1/device/worker-command',headers=h,json={'assignmentId':'x','epoch':1,'workerId':'x','action':'poll'}).status_code==401
    assert r.devices()[0]['approvalStatus']=='REVOKED'


def test_revoked_coordinator_can_finish_drain_but_cannot_start_workers(lab):
    c,s,r,a=lab;d,h=pair(lab);w,wh=pair(lab,'worker',False)
    enable(lab,d,h);enable(lab,w,wh)
    rid=queued(lab,d,workerIds=[w['workerId']]);s.dispatch_once();assignment=r.runs()[0]
    assert c.patch('/api/v1/platform/devices/'+d['deviceId'],headers=a,json={'approved':False}).status_code==200
    command={'assignmentId':assignment['assignmentId'],'epoch':1,'workerId':w['workerId'],'recoveryIndex':0}
    assert c.post('/api/v1/device/worker-command',headers=h,json={**command,'action':'start'}).status_code==401
    process={'assignmentId':assignment['assignmentId'],'epoch':1,'workerAlive':False,'coordinatorAlive':False}
    boot(c,wh,'boot-1',processes=[process])
    poll=c.post('/api/v1/device/worker-command',headers=h,json={**command,'action':'poll'})
    assert poll.status_code==200 and poll.json()['alive'] is False
    report={'sequence':1,'assignmentId':assignment['assignmentId'],'epoch':1,
        'snapshot':{'state':{'status':'CANCELLED'},'generations':[],'candidates':[],'attempts':[],'events':[],'artifacts':[]}}
    boot(c,h,'boot-1',processes=[process],reports=[report]);s.dispatch_once()
    assert s.get(rid)['status']=='CANCELLED' and not r.reservations()
    # Drain authority ends with the released assignment.
    assert c.post('/api/v1/device/worker-command',headers=h,json={**command,'action':'poll'}).status_code==401


def test_reports_deduplicate_and_reject_worker_fabricated_snapshot(lab):
    c,s,r,a=lab;d,h=pair(lab);worker,wh=pair(lab,'second',coordinator=False)
    enable(lab,d,h);enable(lab,worker,wh)
    rid=queued(lab,d,workerIds=[d['workerId'],worker['workerId']]);s.dispatch_once()
    ar=r.runs()[0]
    report={'sequence':1,'assignmentId':ar['assignmentId'],'epoch':ar['epoch'],
            'snapshot':{'state':{'status':'RUNNING'},'generations':[],'candidates':[],'attempts':[],'events':[],'artifacts':[]}}
    boot(c,wh,'boot-1',contribution=True,reports=[report])
    assert r.snapshot(rid)['state']['status']=='STARTING'
    boot(c,h,'boot-1',contribution=True,reports=[report])
    boot(c,h,'boot-1',contribution=True,reports=[{**report,'snapshot':{**report['snapshot'],'state':{'status':'FAILED'}}}])
    assert r.snapshot(rid)['state']['status']=='RUNNING'


def test_coordinator_reserved_even_when_not_candidate_worker(lab):
    c,s,r,a=lab;d,h=pair(lab);w,wh=pair(lab,'worker-only',False)
    enable(lab,d,h);enable(lab,w,wh)
    rid=queued(lab,d,workerIds=[w['workerId']]);s.dispatch_once()
    assert {x['deviceId'] for x in r.reservations()}=={d['deviceId'],w['deviceId']}


def test_device_owner_cannot_execute_shell_or_impersonate_coordinator(lab):
    c,s,r,a=lab;d,h=pair(lab)
    assert c.post('/api/v1/device/worker-command',headers=h,json={'kind':'SHELL','argv':['touch','/tmp/forbidden']}).status_code==422
    enable(lab,d,h);rid=queued(lab,d);s.dispatch_once();ar=r.runs()[0]
    request={'assignmentId':ar['assignmentId'],'epoch':ar['epoch'],'workerId':'not-selected','action':'start','recoveryIndex':0}
    assert c.post('/api/v1/device/worker-command',headers=h,json=request).status_code==403


def test_start_is_durable_before_first_worker_ack(lab):
    c,s,r,a=lab;d,h=pair(lab);w,wh=pair(lab,'worker-only',False)
    enable(lab,d,h);enable(lab,w,wh);rid=queued(lab,d,workerIds=[w['workerId']]);s.dispatch_once()
    ar=r.runs()[0]
    result=c.post('/api/v1/device/worker-command',headers=h,json={'assignmentId':ar['assignmentId'],'epoch':ar['epoch'],'workerId':w['workerId'],'action':'start','recoveryIndex':0})
    assert result.status_code==200 and result.json()['alive'] is None
    assert any(cmd['kind']=='START_WORKER' for cmd in r.commands(w['deviceId']))


def test_restore_mismatch_quarantine_survives_restart(lab):
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h);rid=queued(lab,d);s.dispatch_once();ar=r.runs()[0]
    boot(c,h,'boot-1',contribution=True,processes=[{'assignmentId':ar['assignmentId'],'epoch':ar['epoch'],'workerAlive':False,'events':[{'failure':'RESTORE_MISMATCH'}]}])
    assert r.devices()[0]['approvalStatus']=='QUARANTINED'
    assert d['workerId'] in r.capabilities()['quarantinedWorkerIds']
    again=AgentRuntime();again.attach_store(s)
    assert again.devices()[0]['approvalStatus']=='QUARANTINED'
    assert c.patch('/api/v1/platform/devices/'+d['deviceId'],headers=a,json={'approved':True,'workspaceId':'lab'}).status_code==409


def test_monitoring_events_deduplicate_independently_of_snapshot_sequence(lab):
    import hashlib
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h);rid=queued(lab,d);s.dispatch_once();ar=r.runs()[0]
    event={'event':'generation_done','generation':0,'t':100}
    eid=hashlib.sha256((ar['assignmentId']+json.dumps(event,sort_keys=True,separators=(',',':'))).encode()).hexdigest()
    envelope={'eventId':eid,'assignmentId':ar['assignmentId'],'epoch':1,'event':event}
    for _ in range(2):
        response=boot(c,h,'boot-1',contribution=True,events=[envelope])
        assert response['acceptedEvents']==[eid]
    result=c.get('/api/v1/experiments/'+rid+'/monitoring-events',headers=a)
    assert result.status_code==200 and len(result.json())==1


def test_agent_database_cannot_be_opened_by_legacy_dispatcher(lab):
    from backend.store import Store
    from test_api import Runtime
    _,s,_,_=lab
    with pytest.raises(RuntimeError,match='requires agent mode'):Store(s.path,{},Runtime())


def test_backup_policy_change_does_not_mutate_frozen_assignment(lab):
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h);rid=queued(lab,d);s.dispatch_once()
    original=s.get(rid);hash_before=original['configHash']
    result=c.patch('/api/v1/experiments/'+rid+'/backup-policy',headers=a,json={'interval':2,'retain':5})
    assert result.status_code==200 and result.json()['appliesBeforeNextGeneration']
    assert s.get(rid)['configHash']==hash_before
    assert s.get(rid)['backupPolicy']=={'interval':1,'retain':3}
    assert s.get(rid)['requestedBackupPolicy']=={'interval':2,'retain':5}
    s.dispatch_once()
    assert len(r.runs())==1
    assert any(cmd['kind']=='UPDATE_BACKUP_POLICY' for cmd in r.commands(d['deviceId']))
