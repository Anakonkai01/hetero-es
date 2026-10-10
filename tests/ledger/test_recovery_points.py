import hashlib
import json
from pathlib import Path
import sqlite3
import pytest
from heteroes.product.recovery import capture_point, restore_point, publish_new_directory


def sample(tmp_path):
    root=tmp_path/'run';root.mkdir();(root/'weights').mkdir()
    payload=b'canonical toy checkpoint';sha=hashlib.sha256(payload).hexdigest()
    (root/'weights'/f'{sha}.bin').write_bytes(payload)
    (root/'config.json').write_text(json.dumps({'runId':'a'*32,'maxGenerations':2}))
    with sqlite3.connect(root/'ledger.sqlite') as db:
        db.execute('CREATE TABLE generation_update(generation INTEGER,child_weights_sha256 TEXT,parent_weights_sha256 TEXT,applied_at REAL)')
        db.execute('INSERT INTO generation_update VALUES (0,?,?,1)',(sha,sha))
    return root,sha


def test_snapshot_is_self_contained_and_restores_without_source(tmp_path):
    root,sha=sample(tmp_path)
    point=capture_point(root,{'generation':0,'child_sha256':sha,'parent_sha256':sha}, {'hash':'recipe'}, {'interval':1,'retain':3})
    assert point.is_dir()
    # Capture retains immutable bytes even after canonical file pruning.
    (root/'weights'/f'{sha}.bin').unlink()
    restored=restore_point(point,tmp_path/'restored')
    assert (restored/'weights'/f'{sha}.bin').read_bytes()==b'canonical toy checkpoint'
    assert not (restored/'process.json').exists()
    assert (restored/'dispatch-held.flag').exists()
    with pytest.raises(FileExistsError):restore_point(point,tmp_path/'restored')


def test_corruption_and_pending_publication_cannot_restore(tmp_path):
    root,sha=sample(tmp_path)
    point=capture_point(root,{'generation':0,'child_sha256':sha,'parent_sha256':sha},{},{'interval':1,'retain':3})
    (point/'ledger.sqlite').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):restore_point(point,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_backup_policy_does_not_create_points_between_intervals(tmp_path):
    root,sha=sample(tmp_path)
    assert capture_point(root,{'generation':0,'child_sha256':sha,'parent_sha256':sha},{},{'interval':2,'retain':3}) is None
    assert capture_point(root,{'generation':0,'child_sha256':sha,'parent_sha256':sha},{},{'interval':2,'retain':3},final=True)


def test_restore_publication_refuses_an_empty_competing_destination(tmp_path):
    staging=tmp_path/'staging';staging.mkdir();(staging/'verified').write_text('ready')
    destination=tmp_path/'destination';destination.mkdir()
    with pytest.raises(FileExistsError):publish_new_directory(staging,destination)
    assert not list(destination.iterdir()) and (staging/'verified').exists()


def test_ledger_ahead_of_selected_weights_is_rejected(tmp_path):
    root,sha=sample(tmp_path)
    point=capture_point(root,{'generation':0,'child_sha256':sha,'parent_sha256':sha},{},{'interval':1,'retain':3})
    with sqlite3.connect(point/'ledger.sqlite') as db:db.execute('INSERT INTO generation_update VALUES (1,?,?,2)',(sha,sha))
    manifest=json.loads((point/'manifest.json').read_text())
    manifest['files']['ledger.sqlite']['sha256']=hashlib.sha256((point/'ledger.sqlite').read_bytes()).hexdigest()
    manifest['files']['ledger.sqlite']['sizeBytes']=(point/'ledger.sqlite').stat().st_size
    (point/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='ahead'):restore_point(point,tmp_path/'bad')
