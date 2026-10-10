"""Runtime-owned idle snapshot. Product consumers never open the live ledger."""
import hashlib
import io
import json
import os
import re
import sqlite3
import tarfile
import tempfile
import uuid
from pathlib import Path

from .files import read_json
from .remote import alive


def sha256(path):
    with open(path,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def assert_idle(manager):
    for root in manager.root.iterdir():
        if not root.is_dir():
            continue
        state=manager.state(root)
        if state.get('status') not in ('COMPLETED','CANCELLED','FAILED'):
            raise RuntimeError('Runtime ownership is not idle')
        if alive(read_json(root/'process.json')):
            raise RuntimeError('A coordinator is still alive')
        if any(not v.get('notStarted') and (v.get('alive') or not v.get('confirmed'))
               for v in state.get('workerStates',{}).values()):
            raise RuntimeError('Worker shutdown is unconfirmed')


def backup_path(manager,backup_id):
    if not re.fullmatch('[a-f0-9]{32}',backup_id):
        raise ValueError('Invalid backup ID')
    path=manager.root.parent/'runtime-backups'/(backup_id+'.tar')
    if not path.is_file():
        raise FileNotFoundError()
    return path


def create_backup(manager,maintenance_id):
    with manager.lock:
        manager.check_maintenance(maintenance_id)
        assert_idle(manager)
        output=manager.root.parent/'runtime-backups'
        output.mkdir(mode=0o700,exist_ok=True)
        backup_id=uuid.uuid4().hex
        path=output/(backup_id+'.tar')
        temporary=path.with_suffix('.partial')
        files={}
        try:
            with tempfile.TemporaryDirectory(dir=output) as scratch,tarfile.open(temporary,'w') as archive:
                os.chmod(temporary,0o600)
                for source in sorted(manager.root.rglob('*')):
                    if source.is_symlink():
                        raise ValueError('Runtime snapshot refuses symlink sources')
                    if not source.is_file():
                        continue
                    relative=source.relative_to(manager.root)
                    if relative.name in ('process.json','maintenance.json','start.flag','cancel.flag','workers-stopped.flag') or relative.name.endswith(('-wal','-shm','.tmp')):
                        continue
                    if relative.parts[0]!='quarantine.json' and not re.fullmatch('[a-f0-9]{32}',relative.parts[0]):
                        raise ValueError('Unexpected runtime state entry')
                    copy=source
                    if source.name=='ledger.sqlite':
                        copy=Path(scratch)/(relative.parts[0]+'.sqlite')
                        with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as live,sqlite3.connect(copy) as destination:
                            live.backup(destination)
                    files[relative.as_posix()]={'sha256':sha256(copy),'sizeBytes':copy.stat().st_size}
                    archive.add(copy,arcname=relative.as_posix(),recursive=False)
                payload=json.dumps({'formatVersion':1,'component':'heteroes-runtime','files':files},sort_keys=True).encode()
                entry=tarfile.TarInfo('manifest.json');entry.size=len(payload);entry.mode=0o600
                archive.addfile(entry,io.BytesIO(payload))
            with open(temporary,'rb') as stream:
                os.fsync(stream.fileno())
            temporary.replace(path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return {'backupId':backup_id,'sizeBytes':path.stat().st_size,'sha256':sha256(path),'formatVersion':1}
