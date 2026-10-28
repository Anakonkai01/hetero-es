"""Verify all three hosts, trained states, EOS and sealed receipts; write a fresh summary with --out."""
import argparse
import json
import statistics
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--without-native', action='store_true', help='Explicit partial report; native acceptance stays pending')
p.add_argument('--native-dir', type=Path, help='Fresh follow-up folder with native receipts; never modify this sealed folder')
a = p.parse_args()
here = Path(__file__).resolve().parent
raw = here / 'raw'
load = lambda path: json.loads(path.read_text(encoding='utf-8'))
summary = {'runtimeCommit': '2eb4da0d', 'testFixCommit': '6cc69d26', 'throughput': [], 'parity': {}}
hosts = [('5070ti-linux', '5070ti-01', '5070ti-01[ab]', ('qwen', 'smol', 'tiny')),
         ('3060-wsl2', '3060-wsl2-01', '3060-0[12]', ('qwen', 'smol', 'tiny')),
         ('3060-native', '3060-native-01', 'native-0[12]', ('qwen',))]
if a.without_native:
    hosts = hosts[:2]
for host, directory, pattern, models in hosts:
    for model in models:
        folder = a.native_dir if host == '3060-native' and a.native_dir else raw / directory
        paths = {v: sorted(folder.glob(f'single-{model}-{v}-{pattern}.json')) for v in ('base', 'new')}
        assert all(len(rows) == 2 for rows in paths.values()), (host, model, paths)
        reports = {v: [load(path) for path in rows] for v, rows in paths.items()}
        for case in reports['base'][0]['cases']:
            name = case['case']
            rows = {v: [next(c for c in report['cases'] if c['case'] == name) for report in reports[v]] for v in reports}
            hashes = {row['tokensSha256'] for group in rows.values() for row in group}
            assert len(hashes) == 1, (host, model, name, hashes)
            rates = {v: statistics.median(c['medianTokensPerSecond'] for c in group) for v, group in rows.items()}
            summary['throughput'].append(dict(host=host, model=model, case=name,
                base=round(rates['base'], 1), new=round(rates['new'], 1),
                gainPercent=round(100 * (rates['new'] / rates['base'] - 1), 2), tokensEqual=True))

for model in ('qwen', 'smol', 'tiny'):
    paths = {'5070ti-linux': raw / '5070ti-01' / f'{model}-parity-5070ti-01.json',
             '3060-wsl2': raw / '3060-wsl2-01' / f'{model}-parity-3060-01.json'}
    if model == 'qwen' and not a.without_native:
        paths['3060-native'] = (a.native_dir or raw / '3060-native-01') / 'qwen-parity-native-01.json'
    reports = {host: load(path) for host, path in paths.items()}
    base = reports['5070ti-linux']
    sealed = load(here.parent / '2026-10-26-strict-fused-finish' / 'raw/5070ti-02' / f'{model}-parity-5070ti-02.json')
    assert all(r['status'] == 'ok' and r['modelFiles'] == base['modelFiles'] and r['schemaHash'] == base['schemaHash'] for r in reports.values())
    assert [c['state'] for c in base['cases']] == ['parent', 'plus', 'minus', 'restored']
    states = []
    for number, state in enumerate(base['cases']):
        for host, report in reports.items():
            other = report['cases'][number]
            assert other['state'] == state['state'], host
            assert other['weightsSha256'] == state['weightsSha256'], host
            assert other['restoreExact'] and other['tileEqualsStream'], host
            assert other['results'] == state['results'], (host, model, state['state'])
        old = sealed['cases'][number]
        assert old['weightsSha256'] == state['weightsSha256'] and old['results'] == state['results'], (model, state['state'])
        states.append({'state': state['state'], 'allHostsAndSealedEqual': True, 'restoreExact': True})
    item = {'hosts': sorted(reports), 'states': states}
    if model == 'qwen':
        expected = base['eosCheck']
        for host, report in reports.items():
            assert report['eosCheck'] == expected and report['eosCheck']['equal'], host
        assert sealed['eosCheck'] == expected
        item['eos'] = {'allHostsAndSealedEqual': True, 'rowsEndingEarly': expected['rowsEndingEarly']}
    summary['parity'][model] = item

if not a.without_native:
    native = load((a.native_dir or raw / '3060-native-01') / 'codex-prefill-native-run-01.json')
    assert native['status'] == 'ok' and native['pytestExitCode'] == 0
    assert native['sourceManifestEqual'] and native['sourceManifestUnchangedAfter']
summary['nativeManifestVerified'] = None if a.without_native else True
summary['nativeAcceptancePending'] = a.without_native
with a.out.open('x') as f:
    json.dump(summary, f, indent=2)
    f.write('\n')
for row in summary['throughput']:
    print(f"{row['host']:14s} {row['model']:5s} {row['case']:8s} {row['base']:8.1f} -> {row['new']:8.1f} ({row['gainPercent']:+.2f}%)")
print('All trained parent/canonical ±/restore, EOS and sealed comparisons passed.')
