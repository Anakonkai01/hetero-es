"""Real manifest/quota logic against an in-memory object service, not cloud evidence."""
import hashlib
import json
import pytest
from backend.cloud_storage import CloudStorage, QuotaExceeded
from backend.devices import AgentRuntime
from backend.store import Store


class Objects:
    def __init__(self):self.data={}
    def inventory(self):return sum(map(len,self.data.values()))
    def get(self,key):yield self.data[key]
    def put(self,key,data):self.data[key]=data
    def publish_upload(self,source,destination,etag):self.data[destination]=self.data.pop(source)
    def delete(self,key):self.data.pop(key,None)
    def upload_plan(self,key,size):return {'mode':'single','key':key,'url':'https://private.invalid/secret','headers':{}}
    def complete(self,key,upload_id,parts):pass
    def abort(self,key,upload_id):pass
    def download_url(self,key):return 'https://private.invalid/secret'


@pytest.fixture
def storage(tmp_path):
    r=AgentRuntime();s=Store(tmp_path/'lab.sqlite',{'admin':'test-admin-pass'},r);objects=Objects()
    return CloudStorage(s,objects,quota_bytes=10000),objects,s


def manifest(payload=b'weights',point='a'*32):
    sha=hashlib.sha256(payload).hexdigest()
    return {'formatVersion':1,'pointId':point,'runId':'b'*32,'generation':0,'final':False,
            'backupPolicy':{'interval':1,'retain':3},'childWeightsSha256':sha,'parentWeightsSha256':sha,
            'files':{'weights/'+sha+'.bin':{'sha256':sha,'sizeBytes':len(payload)},
                     'ledger.sqlite':{'sha256':sha,'sizeBytes':len(payload)},
                     'config.json':{'sha256':sha,'sizeBytes':len(payload)},'identity.json':{'sha256':sha,'sizeBytes':len(payload)}}}


def upload(storage,objects,m,payload=b'weights'):
    plan=storage.begin(m)
    for entry in plan['objects']:objects.put(entry['key'],payload)
    storage.verify(m['pointId'])
    return plan


def test_manifest_published_last_and_contents_deduplicated(storage):
    st,obj,s=storage;m=manifest();plan=st.begin(m)
    assert st.points(m['runId'])[0]['status']=='PENDING'
    assert 'manifests/'+m['pointId']+'.json' not in obj.data
    assert len(plan['objects'])==1
    for entry in plan['objects']:obj.put(entry['key'],b'weights')
    st.verify(m['pointId'])
    assert st.points(m['runId'])[0]['status']=='READY'
    assert json.loads(obj.data['manifests/'+m['pointId']+'.json'])==m


def test_bad_content_never_becomes_ready(storage):
    st,obj,s=storage;m=manifest();plan=st.begin(m)
    obj.put(plan['objects'][0]['key'],b'corrupt')
    with pytest.raises(ValueError,match='checksum'):st.verify(m['pointId'])
    assert st.points(m['runId'])[0]['status']=='ERROR'
    assert 'manifests/'+m['pointId']+'.json' not in obj.data


def test_inflight_reservations_count_and_shared_objects_are_not_deleted(storage):
    st,obj,s=storage
    upload(st,obj,manifest())
    upload(st,obj,manifest(point='c'*32))
    st.delete_point('a'*32)
    assert any(k.startswith('objects/') for k in obj.data)
    assert st.points('b'*32)[0]['status']=='READY'
    st.quota=500
    with pytest.raises(QuotaExceeded):st.begin(manifest(b'x'*2000,point='d'*32))
    assert len(st.points('b'*32))==1


def test_unsafe_paths_and_changed_point_identity_are_rejected(storage):
    st,obj,s=storage;m=manifest();m['files']['../../secret']=m['files']['ledger.sqlite']
    with pytest.raises(ValueError):st.begin(m)
    m=manifest();st.begin(m)
    with pytest.raises(ValueError):st.begin({**m,'generation':1})


def test_metadata_backup_is_consistent_and_keeps_local_copy(storage):
    from backend.cloud_metadata import create_metadata_backup
    from pathlib import Path
    import sqlite3
    st,obj,s=storage;st.quota=1_000_000
    result=create_metadata_backup(s,st)
    assert result['status']=='READY'
    path=Path(s.path).parent/'metadata-backups'/result['pointId']/'product.sqlite'
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM users').fetchone()[0]==1
    st.quota=1
    result=create_metadata_backup(s,st)
    assert result['status']=='PENDING'
    assert (Path(s.path).parent/'metadata-backups'/result['pointId']/'product.sqlite').exists()


def test_uploaded_object_completion_is_idempotent_and_temp_keys_do_not_change_ready(storage):
    st,obj,s=storage;m=manifest();plan=st.begin(m);entry=plan['objects'][0]
    assert entry['key'].startswith('uploads/')
    obj.put(entry['key'],b'weights')
    st.complete_object(m['pointId'],entry['sha256'],[])
    st.complete_object(m['pointId'],entry['sha256'],[])
    assert st.begin(m)['objects']==[]
    st.verify(m['pointId'])
    obj.put(entry['key'],b'changed-after-verify')
    assert obj.data['objects/'+entry['sha256']]==b'weights'


def test_s3_signed_uploads_use_r2_endpoint_and_fixed_part_sizes():
    from backend.cloud_storage import S3Backend,PART_BYTES
    from urllib.parse import urlparse,parse_qs
    from botocore.stub import Stubber
    backend=S3Backend({'endpointUrl':'https://example.r2.cloudflarestorage.com','bucket':'private',
                       'accessKeyId':'test-access','secretAccessKey':'test-secret','exclusiveAccountConfirmed':True})
    small=backend.upload_plan('uploads/test/object',10)
    assert small['headers']['Content-Length']=='10'
    parsed=urlparse(small['url']);query=parse_qs(parsed.query)
    assert parsed.hostname=='example.r2.cloudflarestorage.com'
    assert query['X-Amz-Expires']==['900']
    assert 'content-length' in query['X-Amz-SignedHeaders'][0]
    with Stubber(backend.client) as stub:
        stub.add_response('create_multipart_upload',{'UploadId':'u'}, {'Bucket':'private','Key':'uploads/test/large'})
        large=backend.upload_plan('uploads/test/large',PART_BYTES+2)
        assert [p['sizeBytes'] for p in large['parts']]==[PART_BYTES,2]
        assert parse_qs(urlparse(large['parts'][1]['url']).query)['partNumber']==['2']
        stub.add_response('copy_object',{}, {'Bucket':'private','Key':'objects/test','CopySource':{'Bucket':'private','Key':'uploads/test/large'},'CopySourceIfMatch':'etag'})
        stub.add_response('delete_object',{}, {'Bucket':'private','Key':'uploads/test/large'})
        backend.publish_upload('uploads/test/large','objects/test','etag')
        stub.assert_no_pending_responses()
    reserved=[]
    with Stubber(backend.client) as stub:
        stub.add_response('list_objects_v2',{'Contents':[{'Key':'object','Size':6}],'IsTruncated':False},{'Bucket':'private'})
        stub.add_response('list_multipart_uploads',{'Uploads':[],'IsTruncated':False},{'Bucket':'private'})
        assert backend.inventory(lambda:reserved.append(1))==6
        assert len(reserved)==4
        stub.assert_no_pending_responses()
