"""Recompute selected timings and compare independent host candidate receipts."""
import hashlib
import json
from pathlib import Path
import statistics

root = Path('docs/evidence/2026-10-25-b22-core-perf')
out = root / 'model-comparison-01.json'
assert not out.exists()
report = {'sourceCommit': '9acf8bfa', 'timings': [], 'models': {}, 'inputs': {}}

def read(path):
    report['inputs'][str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())

for model in ('smol', 'qwen', 'tiny'):
    bench = {}
    candidate = {}
    for host, folder in (('5070ti', 'raw'), ('3060', 'remote-selected-01')):
        x = read(root / folder / f'{model}-selected-{host}-01.json')
        bench[host] = x
        assert x['identities']['baseline']['weightLoadEffective'] == 'scalar'
        assert x['identities']['pairload']['weightLoadEffective'] == ('paired' if host == '5070ti' else 'scalar')
        for case, published in zip(x['cases'], x['comparisons'], strict=True):
            assert case['batch'] == published['batch']
            times = {name: [] for name in ('baseline', 'pairload')}
            tokens = case['records'][0]['tokens']
            assert len(tokens) == case['batch'] and all(len(row) == 32 for row in tokens)
            assert [r['variant'] for r in case['records']] == ['baseline', 'pairload', 'pairload', 'baseline']
            for record in case['records']:
                assert record['repeatTokensEqual'] and record['tokens'] == tokens
                assert len(record['seconds']) == 5 and all(t > 0 for t in record['seconds'])
                times[record['variant']].extend(record['seconds'])
            before, after = (32 * case['batch'] / statistics.median(times[name]) for name in times)
            for key, actual in (('before', before), ('after', after), ('ratio', after / before)):
                assert abs(actual - published[key]) < 1e-9
            report['timings'].append({'model': model, 'host': host, 'batch': case['batch'],
                                      'before': before, 'after': after, 'ratio': after / before,
                                      'spreadPercent': {name: (max(v)-min(v))/statistics.median(v)*100
                                                        for name,v in times.items()}})
        candidate[host] = read(root / folder / f'{model}-candidates-{host}-01.json')
        c = candidate[host]
        assert c['status'] == 'ok' and c['hardwareQualified'] is False
        assert c['modelFiles'] == x['modelFiles']
        assert c['seed'] == 7001 and c['sigma'] == 1e-3
        assert [v['state'] for v in c['cases']] == ['parent','plus','minus','restored']
        for state in c['cases']:
            assert state['restoreExact']
            left, right = (state['engines'][name] for name in ('scalar','selected'))
            for key in ('tokens','texts','rewards','prefillLogitsSha256'):
                assert left[key] == right[key], (host,model,state['state'],key)
            assert left['packedFirstRowLogitsEqualSerial'] and right['packedFirstRowLogitsEqualSerial']
        assert c['cases'][0]['weightsSha256'] == c['cases'][3]['weightsSha256'] == c['parentSha256']
        assert c['cases'][1]['weightsSha256'] != c['parentSha256']
        assert c['cases'][2]['weightsSha256'] != c['parentSha256']
    local, remote = (candidate[h] for h in ('5070ti','3060'))
    for key in ('modelFiles','schemaHash','parentSha256','promptTokenIds','noiseEngine','sourceSha256'):
        assert local[key] == remote[key], (model,key)
    for left,right in zip(bench['5070ti']['cases'],bench['3060']['cases'],strict=True):
        assert left['records'][0]['tokens'] == right['records'][0]['tokens']
    for left,right in zip(local['cases'],remote['cases'],strict=True):
        assert left['weightsSha256'] == right['weightsSha256']
        for key in ('tokens','texts','rewards','prefillLogitsSha256'):
            assert left['engines']['selected'][key] == right['engines']['selected'][key], (model,left['state'],key)
    report['models'][model] = {'crossHostParentBenchmarkTokensEqual': True,
                              'crossHostCandidateWeightsTokensTextsRewardsLogitsEqual': True,
                              'restoreExactAllStates': True,
                              'candidateGeneratedTokenPositionsPerHostPerExecution': 4*8*32,
                              'modelFiles': local['modelFiles'], 'schemaHash': local['schemaHash']}
with out.open('x') as f:
    json.dump(report,f,indent=2)
    f.write('\n')
for t in report['timings']:
    print(t['model'],t['host'],t['batch'],round(t['before'],1),round(t['after'],1),round((t['ratio']-1)*100,2))
print('All finite candidate and timing comparisons passed')
