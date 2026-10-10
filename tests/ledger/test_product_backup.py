"""Maintenance excludes launch; runtime snapshots preserve evidence without PIDs."""
import json
import tarfile

import pytest

from heteroes.product.gateway import Manager
from heteroes.product.files import write_json
from test_product_gateway import manager, config


def test_maintenance_refuses_active_and_unknown_shutdown(manager):
    manager.submit(config())
    with pytest.raises(RuntimeError):
        manager.acquire_maintenance()
    root=manager.directory('a'*32)
    manager.save(root,status='FAILED',workerStates={'local':{'alive':False,'confirmed':False}})
    with pytest.raises(RuntimeError):
        manager.acquire_maintenance()
    manager.save(root,workerStates={'local':{'alive':False,'confirmed':True}})
    hold=manager.acquire_maintenance()
    with pytest.raises(RuntimeError):
        manager.submit(config('b'*32))
    # Durable hold survives service reconstruction.
    resumed=Manager(manager.config,manager.token)
    with pytest.raises(RuntimeError):
        resumed.submit(config('b'*32))
    with pytest.raises(RuntimeError):
        resumed.release_maintenance('wrong')
    resumed.release_maintenance(hold['maintenanceId'])
    resumed.submit(config('b'*32))


def test_snapshot_requires_hold_preserves_history_and_excludes_process_identity(manager):
    manager.submit(config())
    root=manager.directory('a'*32)
    manager.save(root,status='COMPLETED')
    write_json(root/'process.json',{'pid':99999999,'birth':'old'})
    write_json(manager.root/'quarantine.json',{'remote':{'runId':root.name,'t':123}})
    (root/'weights').mkdir();(root/'weights'/'example.bin').write_bytes(b'canonical-weights')
    with pytest.raises(RuntimeError):
        manager.create_backup('no-hold')
    hold=manager.acquire_maintenance()
    result=manager.create_backup(hold['maintenanceId'])
    path=manager.backup_path(result['backupId'])
    with tarfile.open(path) as archive:
        names=archive.getnames()
        assert root.name+'/state.json' in names
        assert root.name+'/process.json' not in names
        assert archive.extractfile(root.name+'/weights/example.bin').read()==b'canonical-weights'
        manifest=json.load(archive.extractfile('manifest.json'))
        assert manifest['formatVersion']==1
        assert 'quarantine.json' in manifest['files']


def test_runtime_snapshot_rejects_symlink_sources(manager,tmp_path):
    manager.submit(config())
    root=manager.directory('a'*32);manager.save(root,status='COMPLETED')
    (tmp_path/'secret').write_text('secret')
    (root/'secret-link').symlink_to(tmp_path/'secret')
    hold=manager.acquire_maintenance()
    with pytest.raises(ValueError,match='symlink'):
        manager.create_backup(hold['maintenanceId'])


def test_retiring_transfer_archive_keeps_original_run_evidence(manager):
    manager.submit(config())
    root=manager.directory('a'*32);manager.save(root,status='COMPLETED')
    (root/'evidence.txt').write_text('original evidence')
    hold=manager.acquire_maintenance();backup=manager.create_backup(hold['maintenanceId'])
    path=manager.backup_path(backup['backupId'])
    manager.discard_backup(backup['backupId'])
    assert not path.exists()
    assert (root/'evidence.txt').read_text()=='original evidence'


def test_unknown_coordinator_identity_blocks_maintenance(manager):
    manager.submit(config());root=manager.directory('a'*32)
    manager.save(root,status='COMPLETED')
    write_json(root/'process.json',{'pid':99999999,'birth':None})
    with pytest.raises(RuntimeError,match='cannot be confirmed'):
        manager.acquire_maintenance()
