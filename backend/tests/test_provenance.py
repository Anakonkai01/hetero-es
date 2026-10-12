"""Vendored copies of Track A code must match their provenance records and Track A."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND.parent / 'scripts' / 'refresh-monitoring.py'


def provenance_problems(root, ignored=()):
    """Differences between provenance.json and the .py files present in `root`."""
    root = Path(root)
    listed = json.loads((root / 'provenance.json').read_text())['files']
    present = {p.name for p in root.glob('*.py') if p.name not in ignored}
    problems = []
    if set(listed) != present:
        problems.append(f'listed {sorted(listed)} but present {sorted(present)}')
    for name, digest in listed.items():
        path = root / name
        if not path.is_file():
            problems.append(f'{name}: listed but missing')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f'{name}: hash differs from provenance.json')
    return problems


def refresh_script():
    spec = importlib.util.spec_from_file_location('refresh_monitoring', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vendored_collector_provenance_matches_files():
    # __init__.py is written by the refresh script itself, not vendored from Track A.
    assert provenance_problems(BACKEND / 'monitoring', ignored={'__init__.py'}) == []


def test_vendored_study_provenance_matches_files():
    assert provenance_problems(BACKEND / 'study') == []


def test_provenance_check_reports_changed_extra_and_missing_files(tmp_path):
    root = tmp_path / 'monitoring'
    shutil.copytree(BACKEND / 'monitoring', root)
    assert provenance_problems(root, ignored={'__init__.py'}) == []
    (root / 'power.py').write_bytes((root / 'power.py').read_bytes() + b'\n# changed\n')
    assert any('power.py: hash differs' in p for p in provenance_problems(root, {'__init__.py'}))
    (root / 'extra.py').write_text('x = 1\n')
    assert any('extra.py' in p for p in provenance_problems(root, {'__init__.py'}))
    (root / 'energy.py').unlink()
    assert any('energy.py: listed but missing' in p for p in provenance_problems(root, {'__init__.py'}))


def fake_track_a(tmp_path, module):
    source = tmp_path / 'track-a' / 'src' / 'heteroes' / 'product'
    source.mkdir(parents=True)
    for name in module.MODULES:
        shutil.copyfile(BACKEND / 'monitoring' / name, source / name)
    return tmp_path / 'track-a'


def test_refresh_check_accepts_a_matching_track_a_tree(tmp_path):
    module = refresh_script()
    assert module.check(fake_track_a(tmp_path, module), BACKEND / 'monitoring') == []


def test_refresh_check_reports_drift_from_track_a_and_stale_provenance(tmp_path):
    module = refresh_script()
    track_a = fake_track_a(tmp_path, module)
    changed = track_a / 'src' / 'heteroes' / 'product' / 'telemetry.py'
    changed.write_bytes(changed.read_bytes() + b'\n# newer\n')
    assert any('telemetry.py: vendored copy differs from Track A' in p
               for p in module.check(track_a, BACKEND / 'monitoring'))
    stale = tmp_path / 'stale'
    shutil.copytree(BACKEND / 'monitoring', stale)
    record = json.loads((stale / 'provenance.json').read_text())
    record['files']['power.py'] = '0' * 64
    (stale / 'provenance.json').write_text(json.dumps(record))
    assert any('power.py: provenance.json hash is stale' in p
               for p in module.check(fake_track_a(tmp_path / 'again', module), stale))
    del record['files']['power.py']
    (stale / 'provenance.json').write_text(json.dumps(record))
    assert any('provenance.json lists' in p
               for p in module.check(fake_track_a(tmp_path / 'third', module), stale))
