"""Recompute every number in README.md from the raw receipts in this folder; writes summary.json."""
import json
from pathlib import Path

here = Path(__file__).parent
raw = here / 'raw'
load = lambda p: json.loads(p.read_text())
summary = {'throughput': [], 'parity': {}, 'sealedB1ef257a': {}}
for host, folder, suffix in (('5070ti-linux', raw, '5070ti-02'), ('3060-wsl2', raw / '3060-wsl2-02', '3060-02')):
    for model in ('qwen', 'smol', 'tiny'):
        r = load(folder / f'bench-gqa-{model}-{suffix}.json')
        for case in r['cases']:
            t = case['medianTokensPerSecond']
            summary['throughput'].append({'host': host, 'model': model, 'case': case['case'],
                                          'original': round(t['strict_attention'], 1), 'selected': round(t['strict_attention_gqa'], 1),
                                          'gainPercent': round(100 * (case['ratio'] - 1), 1), 'tokensEqual': case['tokensEqual']})
for model in ('qwen', 'smol', 'tiny'):
    hosts = {'5070ti-linux': load(raw / f'{model}-parity-5070ti-02.json'), '3060-wsl2': load(raw / '3060-wsl2-02' / f'{model}-parity-3060-02.json')}
    if model == 'qwen':
        hosts['3060-native-win11'] = load(raw / '3060-native-01' / 'claude-attention-qwen-parity-native-01.json')
    base = hosts['5070ti-linux']
    assert all(h['status'] == 'ok' and h['modelFiles'] == base['modelFiles'] for h in hosts.values())
    states = []
    for i, case in enumerate(base['cases']):
        same = all(h['cases'][i]['weightsSha256'] == case['weightsSha256'] and h['cases'][i]['results'] == case['results'] for h in hosts.values())
        inside = all(h['cases'][i]['originalEqualsSelected'] and h['cases'][i]['restoreExact'] for h in hosts.values())
        states.append({'state': case['state'], 'allHostsEqual': same, 'originalEqualsSelectedOnEveryHost': inside,
                       'workloads': sorted(k for k in case['results']['selected'] if k != 'prefillLogitsSha256')})
    summary['parity'][model] = {'hosts': sorted(hosts), 'states': states}
    sealed = Path('docs/evidence/2026-10-26-strict-prefetch')
    old = {'5070ti': load(sealed / 'raw' / f'{model}-candidates-5070ti-02.json'), '3060': load(sealed / 'remote-final-02' / f'{model}-candidates-3060-02.json')}
    summary['sealedB1ef257a'][model] = all(
        o['cases'][i]['engines']['selected']['tokens'] == c['results']['selected']['short8']['tokens']
        and o['cases'][i]['engines']['selected']['prefillLogitsSha256'] == c['results']['selected']['prefillLogitsSha256']
        for o in old.values() for i, c in enumerate(base['cases']))
native = load(raw / '3060-native-01' / 'claude-attention-native-run-01.json')
summary['native'] = {k: native.get(k) for k in ('status', 'platform', 'gpu', 'cc', 'torch', 'nvrtcResult', 'pytestExitCode', 'sourceFileCount')}
(here / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
for row in summary['throughput']:
    print(f"{row['host']:13s} {row['model']:5s} {row['case']:8s} {row['original']:7.1f} -> {row['selected']:7.1f} ({row['gainPercent']:+.1f}%)")
for model, p in summary['parity'].items():
    print(model, p['hosts'], [(s['state'], s['allHostsEqual'], s['originalEqualsSelectedOnEveryHost']) for s in p['states']])
print('matches sealed b1ef257a receipts:', summary['sealedB1ef257a'])
print('native:', summary['native'])
