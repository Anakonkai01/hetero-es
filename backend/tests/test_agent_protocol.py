"""Capabilities live in an HTTP header, preserving the strict old Poll body."""
import json
import pytest
from test_devices import lab, pair, boot, enable, queued

HEADER='X-HeteroES-Agent-Commands'
CORE={'SET_CONTRIBUTION','COORDINATE','START_WORKER','STOP_WORKER','CANCEL_ASSIGNMENT'}


def poll(client,auth,value=None,**changes):
    headers={k:v for k,v in auth.items() if k.lower()!=HEADER.lower()}
    if value is not None:headers[HEADER]=value
    return client.post('/api/v1/device/poll',headers=headers,json={'bootId':'boot-1','contribution':True,**changes})


def enqueue(runtime,device,kind,dedupe):
    with runtime.store.db() as db:runtime._enqueue(db,device['deviceId'],kind,{},dedupe)


def test_server_sends_only_declared_command_kinds_without_dropping_pending_commands(lab):
    client,store,runtime,_=lab;device,auth=pair(lab)
    enqueue(runtime,device,'FUTURE_KIND','future');enqueue(runtime,device,'CANCEL_ASSIGNMENT','cancel')
    response=poll(client,auth,'CANCEL_ASSIGNMENT,FUTURE_KIND')
    assert response.status_code==200,response.text
    assert [c['kind'] for c in response.json()['commands']]==['CANCEL_ASSIGNMENT']
    with store.db() as db:
        pending=[json.loads(r[0])['kind'] for r in db.execute('SELECT body FROM device_commands WHERE ack=0')]
    assert 'FUTURE_KIND' in pending


def test_no_header_uses_conservative_core_floor_and_empty_header_understands_nothing(lab):
    client,_,runtime,_=lab;device,auth=pair(lab)
    enqueue(runtime,device,'FUTURE_KIND','future');enqueue(runtime,device,'STOP_WORKER','stop')
    assert [c['kind'] for c in poll(client,auth).json()['commands']]==['STOP_WORKER']
    assert poll(client,auth,'').json()['commands']==[]


def test_headerless_agent_is_not_sent_pause_or_policy_commands(lab):
    client,_,runtime,_=lab;device,auth=pair(lab);enable(lab,device,auth)
    queued(lab,device);runtime.store.dispatch_once();assignment=runtime.runs()[0]
    with runtime.store.db() as db:
        for kind in ['PAUSE_ASSIGNMENT','UPDATE_BACKUP_POLICY']:
            runtime._enqueue(db,device['deviceId'],kind,{'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch']},kind)
    commands=poll(client,auth).json()['commands']
    assert all(c['kind'] in CORE for c in commands)
    modern=poll(client,auth,','.join(CORE|{'PAUSE_ASSIGNMENT','UPDATE_BACKUP_POLICY'})).json()['commands']
    assert {'PAUSE_ASSIGNMENT','UPDATE_BACKUP_POLICY'} <= {c['kind'] for c in modern}


def test_agent_missing_core_lifecycle_commands_is_not_admitted_to_new_work(lab):
    client,store,runtime,_=lab;device,auth=pair(lab);enable(lab,device,auth)
    run=queued(lab,device)
    assert poll(client,auth,'CANCEL_ASSIGNMENT').status_code==200
    store.dispatch_once()
    assert store.get(run)['status']=='QUEUED' and runtime.reservations()==[]
    assert 'agent' in store.get(run)['waitingReason'].lower()
    assert poll(client,auth,','.join(CORE)).status_code==200
    store.dispatch_once()
    assert store.get(run)['status']=='STARTING'


@pytest.mark.parametrize('value',['x'*2049,'CANCEL_ASSIGNMENT\nEVIL','CANCEL-ASSIGNMENT',','.join(['CANCEL_ASSIGNMENT']*33)])
def test_malformed_capabilities_are_rejected_before_any_boot_or_report_change(lab,value):
    client,store,_,_=lab;_,auth=pair(lab)
    response=poll(client,auth,value,bootId='bad-boot')
    assert response.status_code==422
    with store.db() as db:assert db.execute('SELECT boot_id FROM devices').fetchone()[0]=='boot-1'


def test_declared_capabilities_preserve_core_cancel_and_enable(lab):
    client,_,_,_=lab;device,auth=pair(lab);enable(lab,device,auth)
    response=poll(client,auth,','.join(CORE))
    assert response.status_code==200
    assert all(c['kind'] in CORE for c in response.json()['commands'])


def test_optional_pause_and_policy_require_support_without_changing_frozen_run(lab):
    client,store,runtime,owner=lab;device,auth=pair(lab);enable(lab,device,auth)
    run=queued(lab,device);store.dispatch_once();before=store.get(run)
    assert poll(client,auth,','.join(CORE)).status_code==200
    response=client.post(f'/api/v1/experiments/{run}/pause',headers=owner)
    assert response.status_code==409,response.text
    assert store.get(run)==before
    response=client.patch(f'/api/v1/experiments/{run}/backup-policy',headers=owner,json={'interval':2,'retain':5})
    assert response.status_code==409,response.text
    assert store.get(run)==before
    assert not any(c['kind'] in ('PAUSE_ASSIGNMENT','UPDATE_BACKUP_POLICY') for c in runtime.commands(device['deviceId']))
    kinds=','.join(CORE|{'PAUSE_ASSIGNMENT','UPDATE_BACKUP_POLICY'})
    assert poll(client,auth,kinds).status_code==200
    assert client.post(f'/api/v1/experiments/{run}/pause',headers=owner).status_code==200
    assert any(c['kind']=='PAUSE_ASSIGNMENT' for c in poll(client,auth,kinds).json()['commands'])
