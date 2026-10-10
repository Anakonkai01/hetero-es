"""Idle product/runtime bundle and new-directory restore with a held queue."""
import hashlib
import ctypes
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import uuid

from fastapi import HTTPException

from .migrations import SCHEMA_VERSION
from .store import ACTIVE, now


def sha256(path):
    with open(path,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def publish_new_directory(staging,destination):
    if sys.platform.startswith('linux'):
        # os.rename can replace an empty directory created between verification
        # and publication. Linux RENAME_NOREPLACE closes that race atomically.
        rename=ctypes.CDLL(None,use_errno=True).renameat2
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(staging),-100,os.fsencode(destination),1)!=0:
            error=ctypes.get_errno()
            raise OSError(error,os.strerror(error),str(destination))
    else:
        # Windows rename already refuses an existing destination directory.
        staging.rename(destination)


def begin_maintenance(store,actor):
    # Serialize with the whole dispatch RPC, not just the local queue claim.
    with store.operation_lock,store.db() as db:
        if json.loads(db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]):
            raise HTTPException(409,'Deployment already held; review operations before resuming')
        if any(b['status'] in ACTIVE for b in store.list()):
            raise HTTPException(409,'Wait for confirmed idle runtime ownership')
        db.execute('UPDATE settings SET value="true" WHERE key="dispatchHold"')
        store.audit(db,actor,'MAINTENANCE_BEGIN','deployment')
    # The durable product hold remains if acquiring runtime ownership is uncertain.
    hold=store.runtime.acquire_maintenance()
    with store.db() as db:
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('maintenanceId',json.dumps(hold['maintenanceId'])))
    return hold['maintenanceId']


def end_maintenance(store,actor):
    with store.operation_lock:
        hold=store.runtime.maintenance()
        if hold:
            store.runtime.release_maintenance(hold['maintenanceId'])
        with store.db() as db:
            db.execute('UPDATE settings SET value="false" WHERE key="dispatchHold"')
            db.execute('DELETE FROM settings WHERE key="maintenanceId"')
            store.audit(db,actor,'MAINTENANCE_END','deployment')


def create_bundle(store,actor):
    maintenance_id=begin_maintenance(store,actor)
    output=Path(store.path).parent/'backups';output.mkdir(mode=0o700,exist_ok=True)
    backup_id=uuid.uuid4().hex;target=output/(backup_id+'.tar')
    partial=target.with_suffix('.partial')
    try:
        with tempfile.TemporaryDirectory(dir=output) as temporary:
            temporary=Path(temporary)
            runtime=store.runtime.backup(maintenance_id)
            runtime_path=temporary/'runtime.tar'
            with open(runtime_path,'wb') as stream:
                os.chmod(runtime_path,0o600)
                for block in store.runtime.backup_stream(runtime['backupId']):
                    stream.write(block)
            if runtime_path.stat().st_size!=runtime['sizeBytes'] or sha256(runtime_path)!=runtime['sha256']:
                raise ValueError('Runtime snapshot checksum mismatch')
            product=temporary/'product.sqlite'
            with store.db() as source,sqlite3.connect(product) as destination:
                source.backup(destination)
            manifest={'formatVersion':1,'component':'heteroes-lab','createdAt':now(),
                      'productSchemaVersion':SCHEMA_VERSION,'files':{
                          'product.sqlite':{'sha256':sha256(product),'sizeBytes':product.stat().st_size},
                          # This private immutable staging file was already fully
                          # checked above; avoid hashing many gigabytes twice.
                          'runtime.tar':{'sha256':runtime['sha256'],'sizeBytes':runtime['sizeBytes']}}}
            with tarfile.open(partial,'w') as archive:
                os.chmod(partial,0o600)
                for p in (product,runtime_path):
                    archive.add(p,arcname=p.name,recursive=False)
                encoded=json.dumps(manifest,sort_keys=True).encode()
                info=tarfile.TarInfo('manifest.json');info.size=len(encoded);info.mode=0o600
                archive.addfile(info,io.BytesIO(encoded))
            partial.replace(target)
        with store.db() as db:
            store.audit(db,actor,'BACKUP_CREATE',backup_id)
        result={'backupId':backup_id,'sizeBytes':target.stat().st_size,'sha256':sha256(target),'createdAt':now()}
        end_maintenance(store,actor)
    except BaseException:
        partial.unlink(missing_ok=True)
        # Fail closed: an administrator explicitly resumes after reviewing failure.
        raise
    try:
        store.runtime.discard_backup(runtime['backupId'])
    except Exception:
        # A completed verified bundle is still valid. Keep the transfer copy
        # if cleanup cannot be confirmed; expose this to the operator.
        result['runtimeTransferRetained']=True
        with store.db() as db:
            store.audit(db,actor,'BACKUP_TRANSFER_RETAINED',runtime['backupId'])
    return result


def bundle_path(store,backup_id):
    if not re.fullmatch('[a-f0-9]{32}',backup_id):
        raise HTTPException(404,'Backup not found')
    path=Path(store.path).parent/'backups'/(backup_id+'.tar')
    if not path.is_file():
        raise HTTPException(404,'Backup not found')
    return path


def extract_verified(path,destination,component):
    """Regular files only, exactly the manifest set; never trust tar extraction."""
    with tarfile.open(path,'r:*') as archive:
        entries=archive.getmembers()
        names=[e.name for e in entries]
        if len(set(names))!=len(names) or 'manifest.json' not in names:
            raise ValueError('Missing manifest or duplicate archive paths')
        for entry in entries:
            relative=PurePosixPath(entry.name)
            if not entry.isfile() or relative.is_absolute() or '..' in relative.parts or '\\' in entry.name or relative.as_posix()!=entry.name:
                raise ValueError('Unsafe archive path or file type')
        manifest_entry=archive.getmember('manifest.json')
        if manifest_entry.size>16*1024*1024:
            raise ValueError('Manifest is too large')
        manifest=json.load(archive.extractfile(manifest_entry))
        if manifest.get('formatVersion')!=1 or manifest.get('component')!=component:
            raise ValueError('Unsupported backup format')
        files=manifest['files']
        if set(files)!=set(names)-{'manifest.json'}:
            raise ValueError('Incomplete or unexpected archive contents')
        if component=='heteroes-lab' and set(files)!={'product.sqlite','runtime.tar'}:
            raise ValueError('Incomplete lab snapshot')
        for name,expected in files.items():
            if component=='heteroes-runtime':
                parts=PurePosixPath(name).parts
                if name!='quarantine.json' and (len(parts)<2 or not re.fullmatch('[a-f0-9]{32}',parts[0])):
                    raise ValueError('Invalid runtime history path')
                if PurePosixPath(name).name in ('process.json','maintenance.json','start.flag','cancel.flag','workers-stopped.flag'):
                    raise ValueError('Live process identity must not be restored')
            entry=archive.getmember(name)
            if entry.size!=expected['sizeBytes']:
                raise ValueError('Snapshot size mismatch')
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            digest=hashlib.sha256()
            with archive.extractfile(entry) as source,open(target,'xb') as output:
                os.chmod(target,0o600)
                while block:=source.read(1024*1024):
                    digest.update(block);output.write(block)
            actual=digest.hexdigest()
            if actual!=expected['sha256']:
                raise ValueError('Snapshot checksum mismatch')
            if component=='heteroes-runtime' and len(PurePosixPath(name).parts)==3 and PurePosixPath(name).parts[1]=='weights' and re.fullmatch('[a-f0-9]{64}\\.bin',PurePosixPath(name).name):
                if actual!=PurePosixPath(name).stem:
                    raise ValueError('Canonical checkpoint hash differs from its identity')
        return manifest


def restore_bundle(bundle,destination):
    destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore requires a new deployment directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(bundle,'r:*') as archive:
        try:
            staging_bytes=archive.getmember('runtime.tar').size*2+archive.getmember('product.sqlite').size*2
        except KeyError:
            raise ValueError('Incomplete lab snapshot') from None
    if shutil.disk_usage(destination.parent).free<staging_bytes+2*1024**3:
        raise ValueError('Insufficient free space for verified restore staging and retained weights')
    staging=Path(tempfile.mkdtemp(prefix='.heteroes-restore-',dir=destination.parent))
    try:
        payload=staging/'payload';payload.mkdir(mode=0o700)
        extract_verified(bundle,payload,'heteroes-lab')
        runs=staging/'runs';runs.mkdir(mode=0o700)
        extract_verified(payload/'runtime.tar',runs,'heteroes-runtime')
        for root in runs.iterdir():
            if root.is_dir():
                state_path=root/'state.json'
                if not state_path.is_file():
                    raise ValueError('Snapshot includes active or incomplete runtime ownership')
                state=json.loads(state_path.read_text())
                if state.get('status') not in ('COMPLETED','CANCELLED','FAILED') or any(
                    not worker.get('notStarted') and (worker.get('alive') or not worker.get('confirmed'))
                    for worker in state.get('workerStates',{}).values()):
                    raise ValueError('Snapshot includes active or incomplete runtime ownership')
        product=staging/'product';product.mkdir(mode=0o700)
        shutil.move(payload/'product.sqlite',product/'product.sqlite')
        with sqlite3.connect(product/'product.sqlite') as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION:
                raise ValueError('Product snapshot integrity or schema mismatch')
            if any(json.loads(r[0])['status'] in ACTIVE for r in db.execute('SELECT body FROM experiments')):
                raise ValueError('Product snapshot includes active work')
            db.execute('DELETE FROM sessions')
            db.execute("DELETE FROM settings WHERE key LIKE 'backupDownload:%'")
            db.execute('UPDATE settings SET value="true" WHERE key="dispatchHold"')
            db.execute('DELETE FROM settings WHERE key="maintenanceId"')
            db.execute('INSERT INTO audit(actor,action,target,created,workspace_id) VALUES (?,?,?,?,NULL)',('restore','RESTORE_HOLD','deployment',now()))
        shutil.rmtree(payload)
        (staging/'restore.json').write_text(json.dumps({'formatVersion':1,'restoredAt':now(),'queueHeld':True,'sessionsRevoked':True,
            'configurationRequired':['productStateDirectory','stateDirectory','processDirectory','workers[].stateDirectory']},indent=2))
        os.chmod(staging/'restore.json',0o600)
        # rename is the only publication step; never overwrite an existing tree.
        if destination.exists():
            raise ValueError('Restore destination appeared during verification')
        publish_new_directory(staging,destination)
    except BaseException:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    return {'deploymentDirectory':str(destination),'queueHeld':True,'sessionsRevoked':True}
