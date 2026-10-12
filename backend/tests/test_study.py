import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.devices import AgentRuntime
from backend.local_storage import LocalBackend
from test_api import login


@pytest.fixture
def study(tmp_path):
    storage=LocalBackend(tmp_path/'objects',tmp_path/'key','http://127.0.0.1:8002')
    runtime=AgentRuntime(storage)
    app=create_app(tmp_path/'lab.sqlite',{'admin':'test-admin-pass'},runtime,dispatch=False)
    with TestClient(app) as client:
        yield client,login(client,'admin'),storage


def manifest():
    files={'config.json':b'{}','model.safetensors':b'fake-test-weights','tokenizer.json':b'{}'}
    return {'formatVersion':1,'modelId':'Qwen/Qwen2.5-0.5B-Instruct','revision':'7ae557604adf67be50417f59c2c2f167def9a775',
            'tokenizerRevision':'7ae557604adf67be50417f59c2c2f167def9a775','format':'safetensors',
            'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}},files


def test_dataset_import_frozen_counts_duplicate_leakage_and_auth(study):
    c,a,b=study
    request={'name':'Math','files':{'all':{'format':'json','content':json.dumps([{'prompt':f'Q{i}','answer':i} for i in range(20)])}}}
    assert c.post('/api/v1/datasets/import',json=request).status_code==401
    response=c.post('/api/v1/datasets/import',headers=a,json=request)
    assert response.status_code==201,response.text
    data=response.json();assert data['counts']=={'train':16,'validation':2,'test':2}
    payload=b''.join(b.get('objects/'+data['objectSha256']))
    assert hashlib.sha256(payload).hexdigest()==data['objectSha256']
    assert len(c.get('/api/v1/datasets',headers=a).json())==1
    request['files']['all']['content']=json.dumps([{'prompt':'duplicate','answer':1}]*20)
    assert c.post('/api/v1/datasets/import',headers=a,json=request).status_code==422


def test_model_upload_hash_verification_and_assignment_scoping(study):
    c,a,b=study;m,files=manifest()
    result=c.post('/api/v1/models/register',headers=a,json={'name':'Qwen upload','manifest':m,'source':'UPLOAD'})
    assert result.status_code==201,result.text
    asset=result.json();assert asset['status']=='AWAITING_FILES'
    route='/api/v1/models/'+asset['id']
    plan=c.post(route+'/upload-plan',headers=a,json={k:len(v) for k,v in files.items()}).json()
    from urllib.parse import urlsplit
    for name,body in files.items():
        r=c.put(urlsplit(plan[name]['url']).path,content=body,headers={'Content-Length':str(len(body))})
        assert r.status_code==200,r.text
    r=c.post(route+'/publish',headers=a)
    assert r.status_code==200 and r.json()['status']=='READY'
    assert c.post('/api/v1/device/study-transfer',json={'sha256':next(iter(m['files'].values()))}).status_code==401


def test_registry_refuses_executable_files_and_unpinned_models(study):
    c,a,_=study;m,_=manifest();m['revision']='main'
    assert c.post('/api/v1/models/register',headers=a,json={'name':'bad','manifest':m}).status_code==422


def test_v2_admission_and_private_transfer_are_bound_to_frozen_epoch(study):
    from test_devices import pair,enable
    c,a,b=study;store=c.app.state.store;runtime=store.runtime
    lab=(c,store,runtime,a);d,device_auth=pair(lab)
    m,_=manifest()
    model=c.post('/api/v1/models/register',headers=a,json={'name':'Qwen ref','manifest':m}).json()
    data=c.post('/api/v1/datasets/import',headers=a,json={'name':'Math','files':{'all':{'format':'json','content':json.dumps([{'prompt':f'Question {i}','answer':i} for i in range(20)])}}}).json()
    body={'name':'V2 test','recipeVersion':2,'modelName':m['modelId'],'modelArtifactId':model['id'],'workerIds':[d['workerId']],
        'coordinatorDeviceId':d['deviceId'],'datasetIds':[data['datasetId']],'task':'text_math_v2','batchSize':4,'sigmaSchedule':'cosine',
        'maxGenerations':2,'candidatesPerGeneration':2,'alpha':.001,'sigma':.001,'decodeEngine':'hf_generate','schedulerPolicy':'greedy','syncMode':'synchronous'}
    assert c.post('/api/v1/experiments',headers=a,json=body).status_code==422
    profile=c.get('/api/v1/devices',headers=a).json()[0]['selfTest']
    profile['recipeVersions']=[1,2]
    profile['qualifiedModelHashes']=[model['manifestHash']]
    profile['compatibility']['recipeV2']={'passed':True,'repeatIdentical':True,'modelManifestHash':model['manifestHash'],
        'recipeHash':'a'*64,'parentSha256':'b'*64,'restoredSha256':'b'*64,'perturbedSha256':'c'*64,'outputsHash':'d'*64}
    assert c.patch('/api/v1/device/qualification',headers=device_auth,json={'bootId':'boot-1','selfTest':profile}).status_code==200
    response=c.post('/api/v1/experiments',headers=a,json=body)
    assert response.status_code==200,response.text
    experiment=response.json()
    assert experiment['datasetObjectSha256']==data['objectSha256']
    assert 'datasetPath' not in experiment
    enable(lab,d,device_auth)
    assert c.post('/api/v1/experiments/'+experiment['experimentId']+'/submit',headers=a).status_code==200
    store.dispatch_once();ar=runtime.runs()[0]
    query={'assignmentId':ar['assignmentId'],'epoch':ar['epoch'],'sha256':data['objectSha256']}
    grant=c.post('/api/v1/device/study-transfer',headers=device_auth,json=query)
    assert grant.status_code==200,grant.text
    assert grant.json()['url'].startswith('http://127.0.0.1:8002/api/v1/local-storage/')
    assert c.post('/api/v1/device/study-transfer',headers=device_auth,json={**query,'epoch':99}).status_code==403
    assert c.post('/api/v1/device/study-transfer',headers=device_auth,json={**query,'sha256':'0'*64}).status_code==403
    assert c.get('/api/v1/datasets',headers={**a,'X-Workspace-Id':'other'}).status_code==403
    m,_=manifest();m['files']['remote.py']='a'*64
    assert c.post('/api/v1/models/register',headers=a,json={'name':'bad','manifest':m}).status_code==422
