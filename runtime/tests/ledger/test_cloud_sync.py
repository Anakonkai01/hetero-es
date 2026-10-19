"""Retention persists cleanup intents and outage errors never kill computation."""
from types import SimpleNamespace
from heteroes.product.cloud_sync import CloudSync
from heteroes.product.files import write_json,read_json


def test_local_retention_remembers_remote_cleanup_across_outage(tmp_path,monkeypatch):
    root=tmp_path/'runs'/'run';root.mkdir(parents=True)
    write_json(root/'assignment.json',{'assignmentId':'a'*32,'epoch':1,'config':{'backupPolicy':{'retain':1}}})
    for generation in range(3):
        point=root/'recovery-points'/str(generation)
        write_json(point/'manifest.json',{'generation':generation,'final':False,'backupPolicy':{'retain':1}})
        write_json(point/'cloud-state.json',{'status':'VERIFYING','remoteCreated':True})
    def offline(*args,**kwargs):raise ConnectionError('CPU is offline')
    agent=SimpleNamespace(root=tmp_path,manager=SimpleNamespace(root=tmp_path/'runs'),call=offline)
    sync=CloudSync(agent);sync.cycle()
    assert [p.name for p in (root/'recovery-points').iterdir()]==['2']
    assert set(read_json(root/'cloud-cleanup.json'))=={'0','1'}
    deleted=[]
    def online(path,body,method=None):
        if method=='DELETE':deleted.append(path);return {'deleted':True}
        return {'status':'READY'}
    agent.call=online;sync.cycle()
    assert len(deleted)==2 and read_json(root/'cloud-cleanup.json')==[]
    assert read_json(root/'cloud-sync.json')['lastCloudGeneration']==2


def test_bad_local_metadata_does_not_terminate_sync_thread(tmp_path,monkeypatch):
    agent=SimpleNamespace(root=tmp_path)
    sync=CloudSync(agent)
    def broken():
        sync.stop.set();raise ValueError('Broken private manifest')
    monkeypatch.setattr(sync,'cycle',broken);sync.run()
    assert read_json(tmp_path/'cloud-error.json')['errorType']=='ValueError'
