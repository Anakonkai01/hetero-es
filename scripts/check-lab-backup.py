#!/usr/bin/env python3
"""Full-size idle backup/restore acceptance; creates a NEW inactive deployment."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid

REPO=Path(__file__).resolve().parents[1]
private=Path(os.environ.get('HETEROES_PRIVATE_CONFIG',str(Path.home()/'.config/heteroes-integration')))
config=json.loads((private/'config.json').read_text());credentials=json.loads((private/'credentials.json').read_text())
base=f"http://127.0.0.1:{config.get('backendPort',8000)}/api/v1";token=None


def call(route,body=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(base+route,headers=headers,data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(request,timeout=1800) as response:return json.load(response)


def rows(path):
    with sqlite3.connect(path) as db:
        return {table:list(db.execute('SELECT * FROM '+table+' ORDER BY rowid')) for table in ('experiments','queue','memberships','workspaces','worker_assignments')}


token=call('/auth/login',{'username':'admin','password':credentials['users']['admin']})['accessToken']
ops=call('/platform/operations')
assert not ops['reservations'] and not ops['dispatchHeld'],'Backup acceptance requires confirmed idle'
state=Path(config['productStateDirectory']).parent
estimated=sum(p.stat().st_size for p in Path(config['stateDirectory']).rglob('*') if p.is_file())
assert shutil.disk_usage(state).free>estimated*3+2*1024**3,'Insufficient free space for snapshot, bundle and inactive restore'
before=rows(Path(config['productStateDirectory'])/'product.sqlite');started=time.time()
print('Starting idle full-size backup; no GPU is acquired',flush=True)
backup=call('/platform/backups',{})
if backup.get('runtimeTransferRetained'):
    assert shutil.disk_usage(state).free>estimated*2+2*1024**3,'Retained runtime transfer must be retired or additional restore space provided'
print('Backup checksum verified; restoring into a new inactive directory',flush=True)
bundle=Path(config['productStateDirectory'])/'backups'/(backup['backupId']+'.tar')
with open(bundle,'rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==backup['sha256']
target=state/('m1-restored-'+uuid.uuid4().hex)
subprocess.run([sys.executable,str(REPO/'scripts/restore-lab.py'),str(bundle),str(target),'--source-config',str(private/'config.json')],check=True)
assert rows(target/'product/product.sqlite')==before
with sqlite3.connect(target/'product/product.sqlite') as db:
    assert db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
    assert db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]=='true'
    bodies=[json.loads(r[0]) for r in db.execute('SELECT body FROM experiments')]
    snapshots={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,snapshot FROM experiments WHERE snapshot IS NOT NULL')}
assert not list((target/'runs').rglob('process.json'))
restored_config=json.loads((target/'private/config.json').read_text());restored_credentials=json.loads((target/'private/credentials.json').read_text())
assert restored_credentials['runtime_token']!=credentials['runtime_token']
assert restored_config['processDirectory']!=config['processDirectory']
assert all(a['stateDirectory']!=b['stateDirectory'] for a,b in zip(restored_config['workers'],config['workers']))
checkpoint_count=0
for body in bodies:
    for artifact in snapshots.get(body['experimentId'],{}).get('artifacts',[]):
        if artifact['type']=='CHECKPOINT':
            assert (target/'runs'/body['experimentId']/'weights'/artifact['name']).is_file()
            checkpoint_count+=1
after=call('/platform/operations');assert not after['dispatchHeld'] and not after['reservations']
evidence={'backupId':backup['backupId'],'bundleSha256':backup['sha256'],'sizeBytes':backup['sizeBytes'],
          'restoredDeployment':str(target),'experimentCount':len(bodies),'retainedCheckpointReferences':checkpoint_count,
          'historicalTablesPreserved':True,'sessionsRevoked':True,'queueHeld':True,'newRuntimeToken':True,
          'separateProcessAndWorkerDirectories':True,'oldProcessRecordsAbsent':True,'originalDeploymentRunning':True,
          'wallSeconds':time.time()-started}
output=Path(config['productStateDirectory'])/'m1-backup-evidence.json';output.write_text(json.dumps(evidence,indent=2));os.chmod(output,0o600)
print('PASS full-size manifest/hash verification, historical IDs/checkpoints, session revocation and inactive held restore: '+str(output),flush=True)
