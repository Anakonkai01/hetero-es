"""Recompute every number in README.md from the raw receipts in this folder; writes summary.json."""
import json
import statistics
from pathlib import Path

here = Path(__file__).parent
raw = here / 'raw'
gqa = here.parent / '2026-10-26-strict-attention-gqa' / 'raw'
load = lambda p: json.loads(p.read_text())
summary = {'throughput': [], 'parity': {}, 'equalsSealedGqa': {}}


def rates(paths):
    runs = [load(p) for p in paths]
    out = {}
    for case in runs[0]['cases']:
        rows = [next(c for c in r['cases'] if c['case'] == case['case']) for r in runs]
        out[case['case']] = (statistics.median(c['medianTokensPerSecond'] for c in rows), {c['tokensSha256'] for c in rows})
    return out


hosts = (('5070ti-linux', raw / '5070ti-02', '5070ti-02[ab]', 'final'), ('3060-wsl2', raw / '3060-wsl2-02', '3060-0[12]', 'final'),
         ('5070ti-linux', raw / '5070ti-01-5cc72926', '5070ti-01[ab]', 'intermediate 5cc72926'),
         ('3060-wsl2', raw / '3060-wsl2-01-5cc72926', '3060-0[12]', 'intermediate 5cc72926'))
for host, folder, pattern, stage in hosts:
    for model in ('qwen', 'smol', 'tiny'):
        paths = {v: sorted(folder.glob(f'single-{model}-{v}-{pattern}.json')) for v in ('base', 'new')}
        if not paths['base'] or not paths['new']:
            continue
        b, n = rates(paths['base']), rates(paths['new'])
        for case in b:
            summary['throughput'].append({'stage': stage, 'host': host, 'model': model, 'case': case,
                                          'baseD4030b52': round(b[case][0], 1), 'new': round(n[case][0], 1),
                                          'gainPercent': round(100 * (n[case][0] / b[case][0] - 1), 1),
                                          'tokensEqual': b[case][1] == n[case][1] and len(b[case][1]) == 1})
for model in ('qwen', 'smol', 'tiny'):
    found = {h: load(p) for h, p in (('5070ti-linux', raw / '5070ti-02' / f'{model}-parity-5070ti-02.json'),
                                     ('3060-wsl2', raw / '3060-wsl2-02' / f'{model}-parity-3060-02.json')) if p.exists()}
    base = found['5070ti-linux']
    assert all(h['status'] == 'ok' and h['modelFiles'] == base['modelFiles'] for h in found.values())
    summary['parity'][model] = {
        'hosts': sorted(found),
        'states': [{'state': c['state'],
                    'allHostsEqual': all(h['cases'][i]['weightsSha256'] == c['weightsSha256'] and h['cases'][i]['results'] == c['results'] for h in found.values()),
                    'tileEqualsStreamAndRestoreExactOnEveryHost': all(h['cases'][i]['tileEqualsStream'] and h['cases'][i]['restoreExact'] for h in found.values())}
                   for i, c in enumerate(base['cases'])],
        'eos': {h: [r['eosCheck']['equal'], r['eosCheck']['rowsEndingEarly'], r['eosCheck']['captured']['tokensSha256']] for h, r in found.items() if 'eosCheck' in r}}
    old = [gqa / f'{model}-parity-5070ti-02.json', gqa / '3060-wsl2-02' / f'{model}-parity-3060-02.json']
    summary['equalsSealedGqa'][model] = all(
        o['cases'][i]['weightsSha256'] == c['weightsSha256'] and o['cases'][i]['results']['selected'] == c['results']['stream']
        for o in map(load, old) for i, c in enumerate(base['cases']))
(here / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
for row in summary['throughput']:
    print(f"{row['stage']:22s} {row['host']:13s} {row['model']:5s} {row['case']:8s} {row['baseD4030b52']:7.1f} -> {row['new']:7.1f} ({row['gainPercent']:+.1f}%) tokensEqual={row['tokensEqual']}")
for model, p in summary['parity'].items():
    print(model, p['hosts'], [(s['state'], s['allHostsEqual'], s['tileEqualsStreamAndRestoreExactOnEveryHost']) for s in p['states']], p['eos'])
print('equal to sealed GQA receipts:', summary['equalsSealedGqa'])
