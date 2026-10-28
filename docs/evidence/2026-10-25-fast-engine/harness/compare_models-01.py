"""Independent finite corpus comparison: weights must match; vendor inference drift is measured."""
import hashlib
import json
from pathlib import Path
import statistics

root = Path('docs/evidence/2026-10-25-fast-engine')
out = root / 'model-comparison-01.json'
assert not out.exists()
report = {'sourceCommit': 'c9a37059', 'models': {}, 'timings': [], 'inputs': {}}

def read(path):
    report['inputs'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())

def agreement(left, right):
    assert len(left) == len(right)
    assert all(len(a) == len(b) for a,b in zip(left,right))
    return {'equalRows': sum(a == b for a,b in zip(left,right)), 'rows': len(left),
            'equalPositions': sum(x==y for a,b in zip(left,right) for x,y in zip(a,b)),
            'positions': sum(map(len,left))}

for model in ('smol','qwen','tiny'):
    hosts = {}
    for host,folder in (('5070ti','raw'),('3060','remote-01')):
        es = read(root/folder/f'{model}-vllm-es-{host}-01.json')
        control = read(root/folder/f'{model}-vllm-{host}-03.json')
        strict_folder = 'raw' if host == '5070ti' else 'remote-selected-01'
        strict = read(root.parent/'2026-10-25-b22-core-perf'/strict_folder/f'{model}-candidates-{host}-01.json')
        assert es['status'] == control['status'] == strict['status'] == 'ok'
        assert es['modelFiles'] == control['modelFiles'] == strict['modelFiles']
        assert es['promptTokenIds'] == control['promptTokenIds'] == strict['promptTokenIds']
        assert es['preparation']['schemaHash'] == strict['schemaHash']
        assert es['preparation']['parentSha256'] == strict['parentSha256']
        assert es['preparation']['allViewStoragesOwnedByVllm'] and es['finalRestore']['parentRestored']
        assert [c['state'] for c in es['cases']] == ['parent','plus','minus','restored']
        comparisons = []
        for case,reference in zip(es['cases'],strict['cases'],strict=True):
            assert case['weightsSha256'] == reference['weightsSha256'], (model,host,case['state'])
            for batch in case['batches']:
                assert len(batch['tokens']) == batch['sequences']
                assert all(len(row) == 32 for row in batch['tokens'])
            comparisons.append({'state':case['state'],
                                'tokensComparedToB22Batch8': agreement(case['batches'][1]['tokens'],reference['engines']['selected']['tokens']),
                                'rewardsEqualB22Rows': sum(a==b for a,b in zip(case['batches'][1]['rewards'],reference['engines']['selected']['rewards'])),
                                'publicationSecondsIncludingRestore':case['publicationSeconds']})
        for es_batch,bare in zip(es['cases'][0]['batches'],control['cases'],strict=True):
            assert es_batch['sequences'] == bare['sequences']
            assert es_batch['repeatTokensEqual'] and bare['repeatTokensEqual']
            assert es_batch['tokens'] == bare['tokens'], (model,host,'bare-vs-ES-parent')
            before = 32*bare['sequences']/statistics.median(bare['seconds'])
            after = 32*es_batch['sequences']/statistics.median(es_batch['seconds'])
            assert abs(before-bare['tokensPerSecondTotal']) < 1e-8
            assert abs(after-es_batch['tokensPerSecondTotal']) < 1e-8
            report['timings'].append({'model':model,'host':host,'batch':bare['sequences'],
                                      'bareVllm':before,'heteroesVllm':after,'ratio':after/before})
        for parent,restored in zip(es['cases'][0]['batches'],es['cases'][3]['batches'],strict=True):
            assert parent['tokens'] == restored['tokens']
        hosts[host] = {'report':es,'strictComparisons':comparisons}
    local,remote = (hosts[h]['report'] for h in ('5070ti','3060'))
    cross = []
    for a,b in zip(local['cases'],remote['cases'],strict=True):
        assert a['state'] == b['state'] and a['weightsSha256'] == b['weightsSha256']
        for left,right in zip(a['batches'],b['batches'],strict=True):
            cross.append({'state':a['state'],'batch':left['sequences'],
                          'tokens':agreement(left['tokens'],right['tokens']),
                          'equalRewardRows':sum(x==y for x,y in zip(left['rewards'],right['rewards']))})
    report['models'][model]={'canonicalWeightsEqualB22BothHosts':True,'restorationExactBothHosts':True,
                             'hostStrictComparisons':{h:x['strictComparisons'] for h,x in hosts.items()},
                             'crossHostInference':cross}
with out.open('x') as f:
    json.dump(report,f,indent=2)
    f.write('\n')
for t in report['timings']:
    if t['batch']==32:
        print(t['model'],t['host'],'B32',round(t['bareVllm'],1),round(t['heteroesVllm'],1),round(t['ratio']*100,2),'%')
for model,data in report['models'].items():
    rows=sum(c['tokens']['rows'] for c in data['crossHostInference'])
    equal=sum(c['tokens']['equalRows'] for c in data['crossHostInference'])
    rewards=sum(c['equalRewardRows'] for c in data['crossHostInference'])
    print(model,'cross-host rows',equal,'/',rows,'reward rows',rewards,'/',rows)
print('Canonical weight, parent control and exact restore checks passed; inference drift recorded without coercion.')
