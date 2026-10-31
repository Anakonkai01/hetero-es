"""Archive the final Part A matrix only after all four current-source receipts pass."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from acceptance.core import source_tree
from acceptance.registry import CHECKS

REPO = Path('/home/pc5070ti/projects/heteroes')
EVIDENCE = Path('/home/pc5070ti/projects/heteroes-evidence/docs/evidence/2026-11-01-review-fixes')
TREE = 'src-ede4338ef54a443a0ecc33a2bc96ea836ea188b856727ed63e095594a7b8b3a4'
EXPECTED = {('local', ('cpu',)): 2,
            ('local', ('gpu', 'perf', 'faults', 'package', 'mutation')): 24,
            ('3060-wsl', ('gpu', 'perf')): 8,
            ('3060-native', ('gpu',)): 3}
assert source_tree(REPO) == (TREE, False), "working source changed"
receipts = {}
for path in (REPO/'docs/acceptance/receipts').glob('*.json'):
    value = json.loads(path.read_text())
    key = value['host'], tuple(value['profiles'])
    if value['tree'] == TREE and key in EXPECTED:
        if key not in receipts or value['finished'] > receipts[key][1]['finished']:
            receipts[key] = (path, value)
assert set(receipts) == set(EXPECTED), f'missing final receipts: {set(EXPECTED)-set(receipts)}'
locations = {}
for pattern in ('*/receipt.json', '*/results/receipt.json'):
    for path in (REPO/'.scratch/accept').glob(pattern):
        value = json.loads(path.read_text())
        if value['tree'] == TREE:
            locations[(value['host'], tuple(value['profiles']), value['finished'])] = path.parent
validated = []
for key, (path, value) in receipts.items():
    assert value['dirty'] is False, (path, 'dirty source')
    assert len(value['results']) == EXPECTED[key], (path, 'wrong check count')
    expected_names = {c.name for c in CHECKS if key[0] in c.hosts and c.profile in key[1]}
    assert {r['name'] for r in value['results']} == expected_names, (path, 'wrong check names')
    out = locations[(*key, value['finished'])]
    for result in value['results']:
        assert result['status'] == 'PASS' and result['returncode'] == 0, (path, result['name'])
        log = REPO/result['log'] if result['host'] == 'local' else out.parent/result['log'].replace('\\', '/')
        assert hashlib.sha256(log.read_bytes()).hexdigest() == result['log_sha256'], log
        if result['counts']:
            assert result['counts']['failed'] == 0 and result['counts']['errors'] == 0
        if result['name'] in ('noise-es-gpu', 'strict-gpu-suite'):
            assert result['counts']['skipped'] == 0
            expected_passed = 572 if result['name'] == 'noise-es-gpu' else {'local':1639, '3060-wsl':1560, '3060-native':956}[value['host']]
            assert result['counts']['passed'] == expected_passed
            if result['name'] == 'strict-gpu-suite' and value['host'] != 'local':
                assert result['counts']['deselected'] == 79
        validated.append((path, value, out, result, log))
assert len(validated) == 37
assert not EVIDENCE.exists(), 'evidence is immutable: select a fresh folder'
EVIDENCE.mkdir()
manifest = []
for path, value in receipts.values():
    dest = EVIDENCE/'receipts'/path.name
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(path, dest)
for path, value, out, result, log in validated:
    dest = EVIDENCE/'logs'/value['host']/result['name']/'output.log'
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(log, dest)
    manifest.append({'receipt': path.name, 'check': result['name'], 'host': value['host'],
                     'source_log': result['log'], 'archived_log': str(dest.relative_to(EVIDENCE)),
                     'sha256': result['log_sha256'], 'counts': result['counts'],
                     'status': result['status']})
    checkdir = log.parent
    reports = list(checkdir.glob('*.json'))
    if result['name'] in ('strict-e2e', 'strict-e2e-soak', 'strict-e2e-int8'):
        reports += list(checkdir.glob('*/report.json'))
    for report in reports:
        target = EVIDENCE/'reports'/value['host']/result['name']/report.relative_to(checkdir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, target)
for name in ('A0-final-proof-audit.json', 'A3-final-proof-audit.json', 'A006-doc-review.json',
             'A006-links-final.json', 'A006-doc-followup.patch', 'A6-final-mutation-audit.json'):
    target = EVIDENCE/'audits'/name
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(REPO/'.scratch/review-2026-11'/name, target)
(EVIDENCE/'verified-logs.json').write_text(json.dumps({'tree': TREE, 'checks': manifest}, indent=2)+'\n')
(EVIDENCE/'README.md').write_text('''# Part A final review acceptance

Source identity `src-ede4338ef54a443a0ecc33a2bc96ea836ea188b856727ed63e095594a7b8b3a4`,
committed source `21d7f591` (source fixes through `a5d81cbd`). All 37 checks passed on this same clean source:
CPU 2/2, local GPU/performance/fault/package/mutation 24/24, RTX 3060 WSL 8/8, native Windows 3/3.
Every copied check log was verified against its original receipt SHA-256 before archival. Receipts are copied without
editing; verified-logs.json maps their original log paths to the immutable archive.

CPU: acceptance selftests 58 passed, runtime 3,324 passed / 1,045 intentionally CUDA-hidden skips,
backend SQLite 464 passed, all 24 check-all steps passed. Full CPU child logs are in
2026-11-01-partA-cpu-ede4338e. GPU noise/ES: 572 passed, zero skips on each of the three GPU environments.
Strict/eval: 1,639 local, 1,560 WSL, 956 native; zero skips. RTX 3060 explicitly deselects 79 SM120-only cases.
Strict Qwen parity passes on all three; Smol/Tiny parity, memory, phase trace and throughput pass on both Linux hosts.
Local short32 reaches 10,100.4 token/s, chat128 9,931.9 token/s, above pinned floors 9,873.1 / 9,753.
Fault/replay, 600-generation soak, int8 lifecycle, both Linux app packages and all twelve mutation groups passed.

P-FROZEN before/after CPU and CUDA bytes and update overhead are retained in 2026-10-31-frozen-fixes.
The final audit rechecks those fingerprints and confirms frozen source is unchanged since 7908609c.
A-014 is the explicitly authorized ledger release-state correction, not an unchanged-state claim.
Network, runtime, harness and documentation proof are indexed in the working branch EVIDENCE-INDEX.md.
The independently measured non-strict SM86 FP16 reference is in 2026-11-01-qwen-fp16-sm86;
the shared strict golden was not changed. Intermediate real failures remain archived in 2026-11-01-partA-matrix-c0d90ddb.

## What this does NOT show

This closes the approved Part A review scope. It does not deploy or restart the live lab, change device approval,
close deferred architecture/full-disk work or the separate managed-runner bookkeeping measurement,
prove PostgreSQL/OIDC/MinIO or MiniCloud acceptance, or show learning. Parts B and C remain to be implemented.
''')
files = sorted(p for p in EVIDENCE.rglob('*') if p.is_file())
(EVIDENCE/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(EVIDENCE)}\n' for p in files))
print(json.dumps({'archive': str(EVIDENCE), 'verified_checks': len(validated), 'files': len(files)+1}))
