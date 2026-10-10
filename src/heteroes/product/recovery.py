"""Small per-generation recovery points. Never copies live WAL or process identity."""
import hashlib
import ctypes
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import sys
import uuid
from .files import write_json

HEX = re.compile(r'[0-9a-f]{64}')


def publish_new_directory(staging,destination):
    """Atomically refuse to replace even an empty competing destination."""
    if sys.platform.startswith('linux'):
        rename=ctypes.CDLL(None,use_errno=True).renameat2
        rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(staging),-100,os.fsencode(destination),1)!=0:
            error=ctypes.get_errno()
            raise OSError(error,os.strerror(error),str(destination))
    else:
        staging.rename(destination)


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_identity(root):
    """Identify exact runtime bytes even on an isolated GPU without Git metadata."""
    root=Path(root)
    files={str(path.relative_to(root)):sha256(path) for path in sorted(root.rglob('*.py'))}
    if not files:raise ValueError('Runtime sources unavailable')
    encoded=json.dumps(files,sort_keys=True,separators=(',',':')).encode()
    return {'sourceTreeSha256':hashlib.sha256(encoded).hexdigest(),'sourceFiles':files}


def safe_name(name):
    if name in ('config.json', 'ledger.sqlite', 'identity.json'):
        return True
    parts=PurePosixPath(name).parts
    return len(parts)==2 and parts[0]=='weights' and HEX.fullmatch(parts[1][:-4]) and parts[1].endswith('.bin')


def capture_point(root, summary, recipe, policy, final=False, identity=None):
    """Called only after publication and before the next generation opens.

    Published weights are immutable: hard links keep them alive through pruning.
    Their filename already carries the runtime-verified publication SHA. Upload
    and restore still verify full bytes outside the generation barrier.
    """
    root=Path(root)
    generation=summary['generation']
    if not final and (generation+1)%policy['interval']:
        return None
    destination=root/'recovery-points'/uuid.uuid4().hex
    temporary=destination.with_name(destination.name+'.pending')
    temporary.mkdir(parents=True,mode=0o700)
    files={}
    try:
        with sqlite3.connect(f'file:{root / "ledger.sqlite"}?mode=ro',uri=True) as source:
            row=source.execute('SELECT child_weights_sha256,applied_at FROM generation_update WHERE generation=?',(generation,)).fetchone()
            if not row or not row[1] or row[0]!=summary['child_sha256']:
                raise ValueError('Recovery point requires a completed published generation')
            with sqlite3.connect(temporary/'ledger.sqlite') as backup:
                source.backup(backup)
        shutil.copyfile(root/'config.json',temporary/'config.json')
        write_json(temporary/'identity.json',{'recipe':recipe,'deployment':identity or {}})
        for name in ('ledger.sqlite','config.json','identity.json'):
            path=temporary/name;os.chmod(path,0o600)
            files[name]={'sha256':sha256(path),'sizeBytes':path.stat().st_size}
        (temporary/'weights').mkdir(mode=0o700)
        for value in {summary['parent_sha256'],summary['child_sha256']}:
            if not HEX.fullmatch(value):raise ValueError('Invalid published hash')
            source=root/'weights'/f'{value}.bin'
            if source.is_symlink() or not source.is_file():raise ValueError('Published weights are missing or unsafe')
            os.link(source,temporary/'weights'/source.name)
            files['weights/'+source.name]={'sha256':value,'sizeBytes':source.stat().st_size}
        manifest={'formatVersion':1,'pointId':destination.name,'runId':json.loads((root/'config.json').read_text())['runId'],
                  'generation':generation,'childWeightsSha256':summary['child_sha256'],'parentWeightsSha256':summary['parent_sha256'],
                  'final':final,'backupPolicy':policy,'files':files}
        write_json(temporary/'manifest.json',manifest)
        publish_new_directory(temporary,destination)
        return destination
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True)
        raise


def verify_point(point):
    point=Path(point)
    manifest=json.loads((point/'manifest.json').read_text())
    if manifest.get('formatVersion')!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Unsupported manifest')
    if not {'ledger.sqlite','config.json','identity.json'}<=manifest['files'].keys():raise ValueError('Incomplete manifest')
    for name,meta in manifest['files'].items():
        if not safe_name(name):raise ValueError('Unsafe recovery path')
        path=point/name
        if any(p.is_symlink() for p in [point,path.parent,path]) or not path.is_file():raise ValueError('Missing or unsafe recovery file')
        if type(meta.get('sizeBytes')) is not int or path.stat().st_size!=meta['sizeBytes'] or sha256(path)!=meta['sha256']:
            raise ValueError('Recovery checksum mismatch')
    if f'weights/{manifest["childWeightsSha256"]}.bin' not in manifest['files']:raise ValueError('Missing canonical child')
    if f'weights/{manifest["parentWeightsSha256"]}.bin' not in manifest['files']:raise ValueError('Missing canonical parent')
    with sqlite3.connect(f'file:{point / "ledger.sqlite"}?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid ledger snapshot')
        row=db.execute('SELECT child_weights_sha256,applied_at FROM generation_update WHERE generation=?',(manifest['generation'],)).fetchone()
        if not row or row[0]!=manifest['childWeightsSha256'] or not row[1]:raise ValueError('Ledger and weights disagree')
        if db.execute('SELECT max(generation) FROM generation_update WHERE applied_at IS NOT NULL').fetchone()[0]!=manifest['generation']:
            raise ValueError('Ledger is ahead of recovery weights')
    if json.loads((point/'config.json').read_text())['runId']!=manifest['runId']:raise ValueError('Run identity mismatch')
    return manifest


def restore_point(point, destination):
    point=Path(point);destination=Path(destination)
    if destination.exists():raise FileExistsError(destination)
    manifest=verify_point(point)
    temporary=destination.with_name(destination.name+'.restoring-'+uuid.uuid4().hex)
    temporary.mkdir(parents=True,mode=0o700)
    try:
        for name in manifest['files']:
            target=temporary/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            shutil.copyfile(point/name,target);os.chmod(target,0o600)
        write_json(temporary/'recovery-lineage.json',manifest)
        write_json(temporary/'backup-policy.json',manifest['backupPolicy'])
        write_json(temporary/'state.json',{'status':'RECOVERING','recoveryCount':0,'workersLaunched':False,
                                         'workerStates':{},'startedAt':__import__('time').time()})
        (temporary/'dispatch-held.flag').touch(mode=0o600)
        publish_new_directory(temporary,destination)
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True)
        raise
    return destination
