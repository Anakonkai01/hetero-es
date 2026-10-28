"""Recompute every number in README.md from the raw receipts in this folder; writes summary.json."""
import json
import statistics
from pathlib import Path

here = Path(__file__).parent
raw = here / 'raw'
gqa = here.parent / '2026-10-26-strict-attention-gqa' / 'raw'
load = lambda p: json.loads(p.read_text())
summary = {'progression5070ti': [], 'throughput': [], 'parity': {}, 'equalsSealedGqa': {}}


def median_rate(paths):
    """Median over runs of each run's median tokens/s, per case; also the token hash every run produced."""
    runs = [load(p) for p in paths]
    out = {}
    for case in runs[0]['cases']:
        rows = [next(c for c in r['cases'] if c['case'] == case['case']) for r in runs]
        out[case['case']] = (statistics.median(c['medianTokensPerSecond'] for c in rows), {c['tokensSha256'] for c in rows})
    return out


# Same-session 5070 Ti progression (each step against its own base, separate processes, ABAB).
for step, base, new in (('stream + queued step (878018e3) vs 75f92c30', 'single-qwen-base-0[12]', 'single-qwen-new-0[12]'),
                        ('+ grouped launches vs 878018e3', 'progression/group-base-0[12]', 'progression/group-new-0[12]'),
                        ('+ fused RMSNorm/SiLU quantization vs 878018e3', 'progression/fused2-base-0[12]', 'progression/fused2-new-0[12]')):
    b, n = median_rate(sorted(raw.glob(base + '.json'))), median_rate(sorted(raw.glob(new + '.json')))
    for case in b:
        summary['progression5070ti'].append({'step': step, 'case': case, 'base': round(b[case][0], 1), 'new': round(n[case][0], 1),
                                             'tokensEqual': b[case][1] == n[case][1] and len(b[case][1]) == 1})
# Final: base 75f92c30 vs HEAD from one stage archive, per host.
hosts = (('5070ti-linux', raw, '0[34]'), ('3060-wsl2', raw / '3060-wsl2-01', '3060-0[12]'), ('3060-native-win11', raw / '3060-native-01', 'native-0[12]'))
for host, folder, rounds in hosts:
    for model in ('qwen', 'smol', 'tiny'):
        paths = {v: sorted(folder.glob(f'single-{model}-{v}-{rounds}.json')) for v in ('base', 'new')}
        if not paths['base']:
            continue
        b, n = median_rate(paths['base']), median_rate(paths['new'])
        for case in b:
            summary['throughput'].append({'host': host, 'model': model, 'case': case, 'base75f92c30': round(b[case][0], 1),
                                          'new': round(n[case][0], 1), 'gainPercent': round(100 * (n[case][0] / b[case][0] - 1), 1),
                                          'tokensEqual': b[case][1] == n[case][1] and len(b[case][1]) == 1, 'runs': len(paths['base'])})
for model in ('qwen', 'smol', 'tiny'):
    receipts = {'5070ti-linux': raw / f'{model}-parity-5070ti-04.json', '3060-wsl2': raw / '3060-wsl2-01' / f'{model}-parity-3060-01.json',
                '3060-native-win11': raw / '3060-native-01' / f'{model}-parity-native-01.json'}
    found = {h: load(p) for h, p in receipts.items() if p.exists()}
    base = found['5070ti-linux']
    assert all(h['status'] == 'ok' and h['modelFiles'] == base['modelFiles'] for h in found.values())
    states = []
    for i, case in enumerate(base['cases']):
        states.append({'state': case['state'],
                       'allHostsEqual': all(h['cases'][i]['weightsSha256'] == case['weightsSha256'] and h['cases'][i]['results'] == case['results'] for h in found.values()),
                       'tileEqualsStreamAndRestoreExactOnEveryHost': all(h['cases'][i]['tileEqualsStream'] and h['cases'][i]['restoreExact'] for h in found.values())})
    eos = {h: {'equal': r['eosCheck']['equal'], 'rowsEndingEarly': r['eosCheck']['rowsEndingEarly'], 'tokensSha256': r['eosCheck']['captured']['tokensSha256']}
           for h, r in found.items() if 'eosCheck' in r}
    summary['parity'][model] = {'hosts': sorted(found), 'states': states, 'eos': eos,
                                'eosEqualAcrossHosts': len({e['tokensSha256'] for e in eos.values()}) <= 1}
    # Sealed GQA receipts (75f92c30 arithmetic, unfused/ungrouped tile projections), both GPUs (+ native Qwen).
    old = [gqa / f'{model}-parity-5070ti-02.json', gqa / '3060-wsl2-02' / f'{model}-parity-3060-02.json']
    if model == 'qwen':
        old.append(gqa / '3060-native-01' / 'claude-attention-qwen-parity-native-01.json')
    summary['equalsSealedGqa'][model] = all(
        o['cases'][i]['weightsSha256'] == c['weightsSha256'] and o['cases'][i]['results']['selected'] == c['results']['stream']
        for o in map(load, old) for i, c in enumerate(base['cases']))
native = raw / '3060-native-01' / 'claude-projection-native-run-01.json'
if native.exists():
    n = load(native)
    summary['native'] = {k: n.get(k) for k in ('status', 'platform', 'gpu', 'cc', 'torch', 'nvrtcResult', 'pytestExitCode', 'sourceFileCount', 'commit')}
(here / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
for row in summary['progression5070ti']:
    print(f"{row['step']:48s} {row['case']:8s} {row['base']:7.1f} -> {row['new']:7.1f} tokensEqual={row['tokensEqual']}")
for row in summary['throughput']:
    print(f"{row['host']:18s} {row['model']:5s} {row['case']:8s} {row['base75f92c30']:7.1f} -> {row['new']:7.1f} ({row['gainPercent']:+.1f}%) tokensEqual={row['tokensEqual']}")
for model, p in summary['parity'].items():
    print(model, p['hosts'], [(s['state'], s['allHostsEqual'], s['tileEqualsStreamAndRestoreExactOnEveryHost']) for s in p['states']], p['eos'] and {h: (e['equal'], e['rowsEndingEarly']) for h, e in p['eos'].items()}, 'eosEqualAcrossHosts', p['eosEqualAcrossHosts'])
print('equal to sealed GQA receipts:', summary['equalsSealedGqa'])
print('native:', summary.get('native'))
