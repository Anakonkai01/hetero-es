#!/usr/bin/env python3
"""Restore a verified CPU metadata backup into a fresh held deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import tempfile
from argon2 import PasswordHasher


def restore(source,manifest,destination,admin_id='admin'):
    source=Path(source);destination=Path(destination)
    if destination.exists():raise FileExistsError(destination)
    data=json.loads(Path(manifest).read_text())
    if data.get('formatVersion')!=1 or data.get('component')!='heteroes-product-metadata':raise ValueError('Unsupported metadata backup')
    with open(source,'rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    if sha!=data['sha256'] or source.stat().st_size!=data['sizeBytes']:raise ValueError('Metadata checksum mismatch')
    with sqlite3.connect(f'file:{source.resolve()}?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid metadata database')
        if db.execute('SELECT value FROM settings WHERE key="controlMode"').fetchone()[0]!='agent-v2':raise ValueError('Expected an M2 agent database')
    destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=Path(tempfile.mkdtemp(dir=destination.parent,prefix='m2-restore-'))
    try:
        (temporary/'state').mkdir(mode=0o700)
        target=temporary/'state/product.sqlite';shutil.copyfile(source,target);os.chmod(target,0o600)
        password=secrets.token_urlsafe(24)
        with sqlite3.connect(target) as db:
            profile=db.execute('SELECT profile FROM users WHERE id=?',(admin_id,)).fetchone()
            if not profile or not json.loads(profile[0]).get('platformAdmin'):raise ValueError('Select the restored platform administrator')
            db.execute('UPDATE users SET hash=? WHERE id=?',(PasswordHasher().hash(password),admin_id))
            db.execute('DELETE FROM sessions')
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('dispatchHold','true'))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cloud_downloads'").fetchone():
                db.execute('DELETE FROM cloud_downloads')
            # Preserve reservations and device identities; an offline former
            # coordinator never becomes permission to launch a replacement.
        for name,value in [('credentials.json',{'users':{admin_id:password}}),('config.json',{'deploymentMode':'agent','productStateDirectory':str(destination/'state')})]:
            path=temporary/name;path.write_text(json.dumps(value,indent=2));os.chmod(path,0o600)
        # publish_new_directory supplies Linux RENAME_NOREPLACE, closing overwrite races.
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from backend.cloud_metadata import publish_new_directory
        publish_new_directory(temporary,destination)
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True);raise
    return {'restored':True,'dispatchHeld':True,'sessionsRevoked':True,'reservationsPreserved':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',required=True,type=Path);p.add_argument('--manifest',required=True,type=Path);p.add_argument('--destination',required=True,type=Path);a=p.parse_args()
    print(json.dumps(restore(a.database,a.manifest,a.destination),indent=2))
