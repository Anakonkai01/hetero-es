"""Independently validate portable identity, numerical equality and paired raw timing arithmetic."""
import hashlib
import json
from pathlib import Path
import statistics

root=Path.cwd()/'docs/evidence/2026-10-25-frozen-subwarp-perf'
target=root/'model-comparison-01.json'
if target.exists():raise FileExistsError(target)
source=json.loads((root/'selected-source-01.json').read_text())
result={'selectedCommit':source['commit'],'scope':'finite pinned parent/probe/canonical plus/minus corpus; two architectures',
        'models':{},'timings':[],'inputs':{}}
for key in ('smol','qwen','tiny'):
    paths={host:root/'raw'/f'{key}-{label}.json' for host,label in
        (('5070ti','selected-paired-5070ti-01'),('3060','paired-3060-01'))}
    docs={host:json.loads(path.read_text()) for host,path in paths.items()}
    local=docs['5070ti'];remote=docs['3060']
    for field in ('bundleSha256','modelFiles','promptTokenIds','generated','prefillLogits','sourceSha256'):
        assert local[field]==remote[field],(key,field)
    assert local['sourceSha256']==source['sourceHashes']['runtime/src/heteroes/eval/strict_cuda.py']
    states={item['state'] for item in local['generated']}
    assert states=={'zero','probe','plus','minus'}
    assert len(local['generated'])==12
    assert len({item['sha256'] for item in local['prefillLogits']})==4,'states must exercise different logits'
    result['models'][key]={'bundleSha256':local['bundleSha256'],'crossGpuTokensTextRewardsEqual':True,
        'crossGpuPrefillLogitsEqual':True,'generatedTokenPositionsPerHost':sum(len(row) for g in local['generated'] for row in g['tokens']),
        'headVariant':local['headVariant'],'onePrimaryWeightSet':local['onePrimaryWeightSet'] and remote['onePrimaryWeightSet']}
    for host,data in docs.items():
        result['inputs'][paths[host].relative_to(root).as_posix()]=hashlib.sha256(paths[host].read_bytes()).hexdigest()
        for case,claimed in zip(data['cases'],data['comparisons'],strict=True):
            observed={'warp':[],'output':[]}
            tokens=None
            assert [r['execution'] for r in case['records']]==['warp','output','output','warp']
            for stage in case['records']:
                assert stage['repeatTokensEqual'] and len(stage['seconds'])==5
                assert all(len(row)==32 for row in stage['tokens']) and len(stage['tokens'])==case['batch']
                assert stage['generatedTokensPerRepeat']==case['batch']*32
                if tokens is None:tokens=stage['tokens']
                assert tokens==stage['tokens']
                assert stage['tokensPerSecondTotal']==32*case['batch']/statistics.median(stage['seconds'])
                observed[stage['execution']].extend(stage['seconds'])
            before=32*case['batch']/statistics.median(observed['warp'])
            after=32*case['batch']/statistics.median(observed['output'])
            assert abs(claimed['warpTokensPerSecond']-before)<1e-9
            assert abs(claimed['outputTokensPerSecond']-after)<1e-9
            assert abs(claimed['ratio']-after/before)<1e-12
            row={'model':key,'gpu':host,'state':case['state'],'batch':case['batch'],'before':before,'after':after,
                'ratio':after/before,'spreadPercent':{label:100*(max(raw)-min(raw))/statistics.median(raw) for label,raw in observed.items()}}
            result['timings'].append(row)
            print(key,host,case['state'],case['batch'],round(before,1),round(after,1),round(100*(after/before-1),1),flush=True)
with target.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
