"""CPU contract checks for maintenance, archive verification and safe restore."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

from backend.backup import create_bundle,restore_bundle,extract_verified,publish_new_directory
from backend.store import Store
from test_api import setup,login,draft


def snapshot(entries,component='heteroes-runtime'):
    buffer=io.BytesIO()
    manifest={'formatVersion':1,'component':component,'files':{k:{'sha256':hashlib.sha256(v).hexdigest(),'sizeBytes':len(v)} for k,v in entries.items()}}
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for name,value in {**entries,'manifest.json':json.dumps(manifest).encode()}.items():
            info=tarfile.TarInfo(name);info.size=len(value);tar.addfile(info,io.BytesIO(value))
    return buffer.getvalue()


def prepare_runtime(runtime):
    history='a'*32
    data=snapshot({history+'/state.json':b'{"status":"COMPLETED"}',history+'/weights/known.bin':b'known-checkpoint',
                   'quarantine.json':b'{"3060":{"runId":"historical","t":1}}'})
    runtime.hold=None
    runtime.acquire_maintenance=lambda:setattr(runtime,'hold',{'maintenanceId':'owned'}) or runtime.hold
    runtime.maintenance=lambda:runtime.hold
    runtime.release_maintenance=lambda _:setattr(runtime,'hold',None)
    runtime.backup=lambda _:{'backupId':'snapshot','sha256':hashlib.sha256(data).hexdigest(),'sizeBytes':len(data)}
    runtime.backup_stream=lambda _:[data]
    runtime.discard_backup=lambda _:None


def test_backup_restore_preserves_uuid_queue_checkpoint_and_revokes_sessions(setup,tmp_path):
    client,store,runtime=setup;prepare_runtime(runtime)
    admin=login(client,'admin');rid=draft(client,admin).json()['experimentId']
    client.post(f'/api/v1/experiments/{rid}/submit',headers=admin)
    result=create_bundle(store,'admin')
    assert runtime.hold is None
    target=tmp_path/'restored';source=Path(store.path).parent/'backups'/(result['backupId']+'.tar')
    restore_bundle(source,target)
    with sqlite3.connect(target/'product/product.sqlite') as db:
        assert db.execute('SELECT id FROM experiments').fetchone()[0]==rid
        assert db.execute('SELECT run_id FROM queue').fetchone()[0]==rid
        assert db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
        assert db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]=='true'
    restored=Store(target/'product/product.sqlite',{},runtime)
    restored.dispatch_once()
    assert runtime.submissions==[]
    assert (target/'runs'/('a'*32)/'weights/known.bin').read_bytes()==b'known-checkpoint'
    assert json.loads((target/'runs/quarantine.json').read_text())['3060']['runId']=='historical'
    with pytest.raises(ValueError,match='new deployment'):
        restore_bundle(source,target)


def test_active_run_blocks_backup_before_runtime_rpc(setup):
    client,store,runtime=setup;prepare_runtime(runtime)
    admin=login(client,'admin');rid=draft(client,admin).json()['experimentId']
    client.post(f'/api/v1/experiments/{rid}/submit',headers=admin);store.dispatch_once()
    result=client.post('/api/v1/platform/backups',headers=admin)
    assert result.status_code==409
    assert runtime.hold is None


def test_uncertain_maintenance_remains_held_and_blocks_submit_and_dispatch(setup):
    client,store,runtime=setup;prepare_runtime(runtime)
    admin=login(client,'admin');rid=draft(client,admin).json()['experimentId']
    def uncertain():
        raise TimeoutError('ownership uncertain')
    runtime.acquire_maintenance=uncertain
    with pytest.raises(TimeoutError):
        create_bundle(store,'admin')
    assert client.post(f'/api/v1/experiments/{rid}/submit',headers=admin).status_code==409
    store.dispatch_once();assert runtime.submissions==[]
    assert client.post('/api/v1/platform/maintenance/resume',json={'workerConfigurationConfirmed':True},headers=admin).status_code==200
    assert client.post(f'/api/v1/experiments/{rid}/submit',headers=admin).status_code==200


@pytest.mark.parametrize('name',['../escape','/absolute','a/../../outside','a\\escape'])
def test_archive_rejects_traversal_before_extraction(tmp_path,name):
    bundle=tmp_path/'bad.tar';bundle.write_bytes(snapshot({name:b'bad'}))
    with pytest.raises(ValueError,match='Unsafe'):
        extract_verified(bundle,tmp_path/'dest','heteroes-runtime')
    assert not (tmp_path/'dest').exists()


def test_corrupt_archive_rejected_and_partial_destination_removed(setup,tmp_path):
    _,store,runtime=setup;prepare_runtime(runtime)
    result=create_bundle(store,'admin')
    original=Path(store.path).parent/'backups'/(result['backupId']+'.tar')
    corrupt=tmp_path/'corrupt.tar'
    with tarfile.open(original) as source,tarfile.open(corrupt,'w') as dest:
        for member in source:
            value=source.extractfile(member).read()
            if member.name=='runtime.tar':
                value=b'X'+value[1:]
            dest.addfile(member,io.BytesIO(value))
    with pytest.raises(ValueError,match='checksum'):
        restore_bundle(corrupt,tmp_path/'restore')
    assert not (tmp_path/'restore').exists()


def test_product_snapshot_cannot_restore_old_process_identity(tmp_path):
    runtime=tmp_path/'runtime.tar';runtime.write_bytes(snapshot({('a'*32)+'/process.json':b'{"pid":1}'}))
    with pytest.raises(ValueError,match='process identity'):
        extract_verified(runtime,tmp_path/'runs','heteroes-runtime')


@pytest.mark.parametrize('kind',[tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.DIRTYPE])
def test_archive_rejects_links_and_directory_members(tmp_path,kind):
    bundle=tmp_path/'link.tar'
    with tarfile.open(bundle,'w') as archive:
        entry=tarfile.TarInfo('manifest.json');entry.type=kind;entry.linkname='/outside'
        archive.addfile(entry)
    with pytest.raises(ValueError,match='Unsafe'):
        extract_verified(bundle,tmp_path/'dest','heteroes-runtime')


def test_archive_rejects_missing_and_duplicate_files(tmp_path):
    path=tmp_path/'duplicate.tar'
    with tarfile.open(path,'w') as archive:
        for _ in range(2):
            entry=tarfile.TarInfo('manifest.json');archive.addfile(entry)
    with pytest.raises(ValueError,match='duplicate'):
        extract_verified(path,tmp_path/'dest','heteroes-runtime')


def test_platform_backup_is_denied_to_workspace_participant(setup):
    client,_,_=setup
    participant=login(client,'participant')
    for method,path in [('post','/platform/backups'),('get','/platform/operations'),('get','/platform/backups'),('get','/platform/users')]:
        assert getattr(client,method)('/api/v1'+path,headers=participant).status_code==403


def test_gpu_off_cancels_jobs_and_reassignment_waits_for_idle(setup):
    client,store,runtime=setup;prepare_runtime(runtime)
    admin=login(client,'admin')
    ids=[draft(client,admin,name=f'GPU job {i}').json()['experimentId'] for i in range(2)]
    for rid in ids:
        client.post(f'/api/v1/experiments/{rid}/submit',headers=admin)
    store.dispatch_once()
    off=client.post('/api/v1/contributions/5070ti',json={'enabled':False},headers=admin)
    assert off.status_code==200 and off.json()['draining']
    assert store.get(ids[0])['cancelRequested']
    assert store.get(ids[1])['status']=='CANCELLED'
    resources=client.get('/api/v1/resources',headers=admin).json()
    assert resources['pools'][0]['drainingWorkerIds']==['5070ti']
    assert '5070ti' in resources['reservedWorkerIds']
    on=client.post('/api/v1/contributions/5070ti',json={'enabled':True,'workspaceId':'lab'},headers=admin)
    assert on.status_code==409
    assert draft(client,admin).status_code==422
    store.dispatch_once()
    on=client.post('/api/v1/contributions/5070ti',json={'enabled':True,'workspaceId':'lab'},headers=admin)
    assert on.status_code==200


def test_native_backup_download_is_one_use_and_bound_to_live_session(setup):
    client,store,runtime=setup;prepare_runtime(runtime)
    admin=login(client,'admin');result=create_bundle(store,'admin');bid=result['backupId']
    prefix=f'/api/v1/platform/backups/{bid}'
    response=client.post(prefix+'/download-ticket',headers=admin)
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    downloaded=client.get(prefix+'/download')
    assert downloaded.status_code==200 and hashlib.sha256(downloaded.content).hexdigest()==result['sha256']
    assert client.get(prefix+'/download').status_code==401
    assert client.post(prefix+'/download-ticket',headers=admin).status_code==200
    assert client.post('/api/v1/auth/logout',headers=admin).status_code==204
    assert client.get(prefix+'/download').status_code==401


def test_newly_configured_gpu_starts_unassigned_and_disabled(setup):
    _,store,runtime=setup
    store.ensure_workers(['5070ti','3060','new-gpu'])
    assert 'new-gpu' not in store.assignments('lab')
    with store.db() as db:
        assert 'new-gpu' in store.disabled_workers(db)
        assert db.execute('SELECT workspace_id FROM worker_assignments WHERE worker_id="new-gpu"').fetchone()[0] is None


def test_restore_publication_cannot_replace_existing_empty_directory(tmp_path):
    staging=tmp_path/'staging';staging.mkdir();(staging/'evidence').write_text('preserve')
    existing=tmp_path/'existing';existing.mkdir()
    with pytest.raises(FileExistsError):
        publish_new_directory(staging,existing)
    assert (staging/'evidence').read_text()=='preserve'
    assert list(existing.iterdir())==[]


def test_restore_rejects_checkpoint_bytes_inconsistent_with_canonical_identity(tmp_path):
    archive=tmp_path/'invalid-checkpoint.tar'
    archive.write_bytes(snapshot({('a'*32)+'/weights/'+('a'*64)+'.bin':b'wrong-canonical-weights'}))
    with pytest.raises(ValueError,match='Canonical checkpoint'):
        extract_verified(archive,tmp_path/'runs','heteroes-runtime')


def test_failed_transfer_cleanup_preserves_verified_combined_backup(setup):
    _,store,runtime=setup;prepare_runtime(runtime)
    def uncertain(_):
        raise TimeoutError('cleanup response lost')
    runtime.discard_backup=uncertain
    result=create_bundle(store,'admin')
    assert result['runtimeTransferRetained'] is True
    assert (Path(store.path).parent/'backups'/(result['backupId']+'.tar')).is_file()
    assert runtime.hold is None
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM audit WHERE action="BACKUP_TRANSFER_RETAINED"').fetchone()[0]==1


def test_dispatch_remains_held_until_complete_bundle_checksum(setup,monkeypatch):
    from backend import backup as module
    _,store,runtime=setup;prepare_runtime(runtime)
    original=module.sha256;checked=[]
    def check(path):
        if path.parent==Path(store.path).parent/'backups' and path.suffix=='.tar':
            with store.db() as db:
                assert json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]) is True
            checked.append(True)
        return original(path)
    monkeypatch.setattr(module,'sha256',check)
    create_bundle(store,'admin')
    assert checked==[True]
