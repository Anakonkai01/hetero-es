"""Hourly consistent product metadata backup; cloud failure leaves a local copy."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid


def create_metadata_backup(store,storage):
    root=Path(store.path).parent/'metadata-backups';root.mkdir(mode=0o700,exist_ok=True)
    point=root/uuid.uuid4().hex;point.mkdir(mode=0o700)
    database=point/'product.sqlite'
    with store.db() as source,sqlite3.connect(database) as destination:source.backup(destination)
    os.chmod(database,0o600)
    with open(database,'rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    data=database.read_bytes()
    manifest={'formatVersion':1,'component':'heteroes-product-metadata','createdAt':time.time(),
              'sha256':sha,'sizeBytes':len(data),'objectKey':'metadata/'+point.name+'/product.sqlite'}
    (point/'manifest.json').write_text(json.dumps(manifest));os.chmod(point/'manifest.json',0o600)
    try:
        with storage.lock:
            usage=storage.usage()
            if usage['observedBytes']+usage['reservedBytes']+len(data)+len(json.dumps(manifest))>storage.quota:
                raise RuntimeError('Cloud quota reached')
            storage._requests(a=2,b=1)
            storage.backend.put(manifest['objectKey'],data)
            check=hashlib.sha256();size=0
            for chunk in storage.backend.get(manifest['objectKey']):check.update(chunk);size+=len(chunk)
            if size!=len(data) or check.hexdigest()!=sha:raise ValueError('Metadata checksum mismatch')
            storage.backend.put('metadata/'+point.name+'/manifest.json',json.dumps(manifest).encode())
        status={'status':'READY','pointId':point.name,'createdAt':manifest['createdAt']}
    except Exception as error:
        status={'status':'PENDING','pointId':point.name,'errorType':type(error).__name__,'createdAt':manifest['createdAt']}
    (point/'cloud-state.json').write_text(json.dumps(status));os.chmod(point/'cloud-state.json',0o600)
    with store.db() as db:db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('metadataBackupStatus',json.dumps(status)))
    points=sorted([p for p in root.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True)
    import shutil
    for old in points[24:]:
        if (old/'cloud-state.json').exists():
            storage._requests(a=2);storage.backend.delete('metadata/'+old.name+'/manifest.json');storage.backend.delete('metadata/'+old.name+'/product.sqlite')
        shutil.rmtree(old)
    return status


def backup_loop(store,storage,stop):
    last=0
    root=Path(store.path).parent/'metadata-backups'
    if root.exists():
        for point in root.glob('*/manifest.json'):
            last=max(last,json.loads(point.read_text())['createdAt'])
    while not stop.wait(60):
        if time.time()-last<3600:continue
        try:create_metadata_backup(store,storage)
        except Exception:pass
        last=time.time()
