"""Workspace and device authorization around private storage download rights."""
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.devices import AgentRuntime
from labkit import login
from labkit import boot, enable, pair, queued
from test_cloud_storage import Objects,manifest


@pytest.fixture
def lab(tmp_path):
    r=AgentRuntime(Objects());app=create_app(tmp_path/'db.sqlite',{'admin':'test-admin-pass','participant':'test-user-pass'},r,dispatch=False)
    with TestClient(app) as c:yield c,app.state.store,r,login(c,'admin')


def test_upload_scope_and_native_download_ticket_revocation(lab):
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h);rid=queued(lab,d);s.dispatch_once();assignment=r.runs()[0]
    m=manifest();m['runId']=rid
    payload={'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],'manifest':m}
    assert c.post('/api/v1/device/recovery-points',headers=h,json={**payload,'epoch':99}).status_code==403
    response=c.post('/api/v1/device/recovery-points',headers=h,json=payload)
    assert response.status_code==200,response.text
    storage=c.app.state.storage
    for obj in response.json()['objects']:storage.backend.put(obj['key'],b'weights')
    storage.verify(m['pointId'])
    participant=login(c,'participant')
    assert c.post('/api/v1/recovery-points/'+m['pointId']+'/download-plan',headers=participant).status_code==404
    sha=m['childWeightsSha256'];artifact=rid+'.'+sha+'.bin'
    ticket=c.post('/api/v1/artifacts/'+artifact+'/download-ticket',headers=a)
    assert ticket.status_code==200,ticket.text
    assert 'HttpOnly' in ticket.headers['set-cookie']
    path=ticket.json()['downloadUrl']
    assert c.get(path,follow_redirects=False).status_code==303
    assert c.get(path,follow_redirects=False).status_code==401
    ticket=c.post('/api/v1/artifacts/'+artifact+'/download-ticket',headers=a)
    assert c.post('/api/v1/auth/logout',headers=a).status_code==204
    assert c.get(ticket.json()['downloadUrl'],follow_redirects=False).status_code==401


def test_worker_device_cannot_upload_coordinator_snapshot(lab):
    c,s,r,a=lab;d,h=pair(lab);w,wh=pair(lab,'secondary',False);enable(lab,d,h);enable(lab,w,wh)
    rid=queued(lab,d,workerIds=[w['workerId']]);s.dispatch_once();assignment=r.runs()[0];m=manifest();m['runId']=rid
    assert c.post('/api/v1/device/recovery-points',headers=wh,json={'assignmentId':assignment['assignmentId'],'epoch':1,'manifest':m}).status_code==403


def test_abandoned_upload_cleanup_preserves_verified_point(lab):
    c,s,r,a=lab;d,h=pair(lab);enable(lab,d,h);rid=queued(lab,d);s.dispatch_once();assignment=r.runs()[0]
    m=manifest();m['runId']=rid
    body={'assignmentId':assignment['assignmentId'],'epoch':1,'manifest':m}
    plan=c.post('/api/v1/device/recovery-points',headers=h,json=body).json()
    auth={'assignmentId':assignment['assignmentId'],'epoch':1}
    path='/api/v1/device/recovery-points/'+m['pointId']
    assert c.request('DELETE',path,headers=h,json={**auth,'epoch':99}).status_code==403
    assert c.request('DELETE',path,headers=h,json=auth).json()['deleted']
    assert not c.app.state.storage.points(rid)
    plan=c.post('/api/v1/device/recovery-points',headers=h,json=body).json()
    for obj in plan['objects']:c.app.state.storage.backend.put(obj['key'],b'weights')
    c.app.state.storage.verify(m['pointId'])
    assert c.request('DELETE',path,headers=h,json=auth).json()['retained']
    assert c.app.state.storage.points(rid)[0]['status']=='READY'


def test_historical_import_requires_final_lineage_and_scoped_admin(lab):
    c,s,r,a=lab
    rid='d'*32;m=manifest();m.update(runId=rid,final=True)
    body={'experimentId':rid,'ownerUserId':'admin','workspaceId':'lab','status':'COMPLETED','modelVersion':m['childWeightsSha256']}
    with s.db() as db:db.execute('INSERT INTO experiments VALUES (?,?,?,NULL)',(rid,'admin',__import__('json').dumps(body)))
    path='/api/v1/experiments/'+rid+'/recovery-import'
    assert c.post(path,headers=a,json={**m,'childWeightsSha256':'0'*64}).status_code==422
    assert c.post(path,headers=login(c,'participant'),json=m).status_code==404
    response=c.post(path,headers=a,json=m)
    assert response.status_code==200,response.text
    for obj in response.json()['objects']:c.app.state.storage.backend.put(obj['key'],b'weights')
    c.app.state.storage.verify(m['pointId'])
    assert c.app.state.storage.points(rid)[0]['status']=='READY'
