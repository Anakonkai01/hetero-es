import json
import sqlite3

import pytest

from backend.doctor import FAIL, PASS, WARN, main, run_checks
from backend.server import initialize


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / 'lab'
    initialize(root, {'username': 'admin', 'password': 'test-password-long', 'host': '127.0.0.1', 'port': 8002,
                      'storageDirectory': str(tmp_path / 'objects')})
    return root


def levels(root):
    return {name: (level, message) for level, name, message in run_checks(root)}


def edit_config(root, **changes):
    path = root / 'config.json'
    path.write_text(json.dumps({**json.loads(path.read_text()), **changes}))


def test_fresh_lab_has_no_failure_but_reports_the_held_queue_and_plain_http(lab):
    result = levels(lab)
    assert FAIL not in {level for level, _ in result.values()}
    assert result['database'][0] == PASS
    assert result['dispatch'][0] == WARN and 'held' in result['dispatch'][1]
    assert result['transport'][0] == WARN and 'not encrypted' in result['transport'][1]


def test_missing_or_unreadable_configuration_fails(tmp_path):
    assert levels(tmp_path / 'nothing')['configuration'][0] == FAIL
    (tmp_path / 'broken').mkdir()
    (tmp_path / 'broken' / 'config.json').write_text('{not json')
    assert levels(tmp_path / 'broken')['configuration'][0] == FAIL


def test_only_agent_mode_is_supported(lab):
    edit_config(lab, deploymentMode='legacy')
    assert levels(lab)['mode'][0] == FAIL


def test_private_address_must_be_numeric_and_private(lab):
    edit_config(lab, apiUrl='http://lab.example.org:8002')
    assert levels(lab)['address'][0] == FAIL
    edit_config(lab, apiUrl='http://8.8.8.8:8002')
    assert levels(lab)['address'][0] == FAIL
    edit_config(lab, apiUrl='http://127.0.0.1:8002')
    assert levels(lab)['address'][0] == WARN and 'this computer' in levels(lab)['address'][1]
    edit_config(lab, apiUrl='http://192.168.1.20:8002')
    assert levels(lab)['address'][0] == PASS


def test_https_private_address_has_no_transport_warning(lab):
    edit_config(lab, apiUrl='https://192.168.1.20:8002')
    assert levels(lab)['transport'][0] == PASS


def test_public_addresses_are_checked_and_temporary_ones_are_flagged(lab):
    assert 'public' not in levels(lab)
    edit_config(lab, publicWebUrl='https://abc-def.trycloudflare.com')
    assert levels(lab)['public'][0] == WARN and 'temporary' in levels(lab)['public'][1]
    edit_config(lab, publicWebUrl='http://lab.example.org')
    assert levels(lab)['public'][0] == FAIL
    edit_config(lab, publicWebUrl='https://lab.example.org', publicComputeUrl='https://compute.example.org')
    assert levels(lab)['public'][0] == PASS


def test_public_installer_downloads_are_reported(lab):
    edit_config(lab, publicWebUrl='https://lab.example.org')
    assert 'private' in levels(lab)['installers'][1]
    edit_config(lab, publicDownloads=True)
    assert 'public' in levels(lab)['installers'][1] and levels(lab)['installers'][0] == PASS


def test_damaged_or_newer_database_fails(lab):
    with sqlite3.connect(lab / 'state' / 'product.sqlite') as db:
        db.execute('PRAGMA user_version=99')
    assert levels(lab)['database'][0] == FAIL and 'newer' in levels(lab)['database'][1]
    (lab / 'state' / 'product.sqlite').write_bytes(b'this is not a database' * 100)
    assert levels(lab)['database'][0] == FAIL


def test_internal_corruption_that_still_opens_is_caught_by_the_integrity_check(lab, tmp_path):
    database = lab / 'state' / 'product.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    data = database.read_bytes()
    size = int.from_bytes(data[16:18], 'big') or 65536
    for page in range(2, len(data) // size + 1):
        broken = bytearray(data)
        broken[(page - 1) * size + 8:page * size] = b'\xff' * (size - 8)
        candidate = tmp_path / 'candidate.sqlite'
        candidate.write_bytes(bytes(broken))
        try:
            with sqlite3.connect(candidate) as db:
                still_readable = db.execute("SELECT value FROM settings WHERE key='dispatchHold'").fetchone() is not None
                damaged = db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok'
        except sqlite3.Error:
            continue
        if still_readable and damaged:
            database.write_bytes(bytes(broken))
            break
    else:
        pytest.fail('no page could be damaged while the database stays readable')
    result = levels(lab)['database']
    assert result[0] == FAIL


def test_storage_directory_is_required_and_free_space_is_judged(lab, tmp_path, monkeypatch):
    assert levels(lab)['storage'][0] == PASS
    import shutil
    monkeypatch.setattr('backend.doctor.shutil.disk_usage', lambda path: shutil._ntuple_diskusage(100 * 10**9, 99 * 10**9, 1 * 10**9))
    assert levels(lab)['storage'][0] == WARN and 'free' in levels(lab)['storage'][1]
    monkeypatch.undo()
    shutil.rmtree(tmp_path / 'objects')
    assert levels(lab)['storage'][0] == FAIL


def test_a_lab_without_online_devices_is_a_warning_not_a_failure(lab):
    assert levels(lab)['devices'][0] == WARN


def test_command_line_exits_nonzero_only_on_failure(lab, capsys):
    assert main(['--private', str(lab)]) == 0
    assert 'PASS' in capsys.readouterr().out
    edit_config(lab, deploymentMode='legacy')
    assert main(['--private', str(lab)]) == 1
    assert 'FAIL' in capsys.readouterr().out


def test_doctor_never_changes_a_lab_file(lab):
    # SQLite may create its -shm/-wal coordination files when it opens a WAL database,
    # even read-only; no real file (configuration, database, keys) may change.
    def snapshot():
        return {p: p.read_bytes() for p in lab.rglob('*') if p.is_file() and not p.name.endswith(('-shm', '-wal'))}
    before = snapshot()
    run_checks(lab)
    assert snapshot() == before
