"""Restore holds unknown reservations and revokes sessions without overwriting."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import pytest
from backend.devices import AgentRuntime
from backend.store import Store

spec=importlib.util.spec_from_file_location('restore_m2',Path(__file__).parents[2]/'scripts/restore-metadata.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_metadata_restore_preserves_unknown_ownership_and_rejects_corruption(tmp_path):
    runtime=AgentRuntime();store=Store(tmp_path/'source.sqlite',{'admin':'original'},runtime)
    with store.db() as db:
        db.execute('INSERT INTO device_reservations VALUES (?,?)',('offline-device','unknown-assignment'))
        db.execute('INSERT INTO sessions VALUES (?,?,?)',('old-session','admin',9999999999))
    source=tmp_path/'snapshot.sqlite'
    with store.db() as old,sqlite3.connect(source) as new:old.backup(new)
    data=source.read_bytes();manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'formatVersion':1,'component':'heteroes-product-metadata','sha256':hashlib.sha256(data).hexdigest(),'sizeBytes':len(data)}))
    target=tmp_path/'fresh';module.restore(source,manifest,target)
    with sqlite3.connect(target/'state/product.sqlite') as db:
        assert db.execute('SELECT count(*) FROM sessions').fetchone()[0]==0
        assert db.execute('SELECT * FROM device_reservations').fetchone()==('offline-device','unknown-assignment')
        assert db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()[0]=='true'
    assert len(json.loads((target/'credentials.json').read_text())['users']['admin'])>=12
    with pytest.raises(FileExistsError):module.restore(source,manifest,target)
    source.write_bytes(b'bad')
    with pytest.raises(ValueError,match='checksum'):module.restore(source,manifest,tmp_path/'corrupt')
    assert not (tmp_path/'corrupt').exists()
