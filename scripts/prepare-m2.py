#!/usr/bin/env python3
"""Create an isolated, held CPU deployment from an idle M1 metadata database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from backend.store import ACTIVE


def private_json(path,value):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with open(path,'w') as stream:
        os.chmod(path,0o600);json.dump(value,stream,indent=2)


def prepare(source,destination,admin_id='admin',backend_port=8002,ui_port=5175):
    destination=Path(destination)
    if destination.exists():raise FileExistsError('Use a new destination directory')
    destination.mkdir(mode=0o700,parents=True)
    state=destination/'state';state.mkdir(mode=0o700)
    database=state/'product.sqlite'
    with sqlite3.connect(f'file:{Path(source).resolve()}?mode=ro',uri=True) as old:
        old.execute('BEGIN')
        rows=old.execute('SELECT body FROM experiments').fetchall()
        if any(json.loads(r[0])['status'] in ACTIVE for r in rows):raise RuntimeError('Wait for confirmed idle before importing M1 metadata')
        if old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='device_reservations'").fetchone():
            if old.execute('SELECT count(*) FROM device_reservations').fetchone()[0]:raise RuntimeError('Agent reservations must be released before migration')
        before={r[0]:r[1] for r in old.execute('SELECT id,body FROM experiments')}
        queue=list(old.execute('SELECT sequence,run_id FROM queue ORDER BY sequence'))
        with sqlite3.connect(database) as new:old.backup(new)
    password=secrets.token_urlsafe(24)
    with sqlite3.connect(database) as db:
        profile=db.execute('SELECT profile FROM users WHERE id=?',(admin_id,)).fetchone()
        if not profile or not json.loads(profile[0]).get('platformAdmin'):raise ValueError('Select the imported platform administrator')
        db.execute('UPDATE users SET hash=? WHERE id=?',(PasswordHasher().hash(password),admin_id))
        db.execute('DELETE FROM sessions')
        db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('dispatchHold','true'))
        db.execute('DELETE FROM settings WHERE key LIKE "backupDownload:%" OR key="maintenanceId"')
        assert before=={r[0]:r[1] for r in db.execute('SELECT id,body FROM experiments')}
        assert queue==list(db.execute('SELECT sequence,run_id FROM queue ORDER BY sequence'))
    os.chmod(database,0o600)
    private_json(destination/'credentials.json',{'users':{admin_id:password}})
    private_json(destination/'config.json',{'deploymentMode':'agent','productStateDirectory':str(state),
        'backendPort':backend_port,'uiPort':ui_port,'uiHost':'127.0.0.1'})
    evidence={'formatVersion':1,'sourceExperimentCount':len(before),'queuePreserved':True,'experimentBodiesPreserved':True,
              'sessionsRevoked':True,'dispatchHeld':True,'cloudAdminPasswordChanged':True}
    private_json(destination/'migration-evidence.json',evidence)
    return evidence


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-db',required=True,type=Path);p.add_argument('--destination',required=True,type=Path)
    a=p.parse_args();print(json.dumps(prepare(a.source_db,a.destination),indent=2))
