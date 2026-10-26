"""Paired identity checks and finite vendor-GEMM counterexamples, no learning inference."""
import copy
import hashlib
import json
from pathlib import Path
from compare_fp16 import compare

root=Path('docs/evidence/2026-10-26-strict-fp16-parity')
paths=[root/'qwen-5070ti-01.json',root/'qwen-3060-01.json']
left,right=[json.loads(p.read_text())for p in paths]
assert left['backendIdentity']==right['backendIdentity'],'Portable backend identity differs'
result={'crossGpu':compare(left,right),'withinGpu':{},
        'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths},
        'limits':'32 prompts, parent and one antithetic seed, 128 outputs. Restored and batch variants '
                 'repeat questions, not independent samples. Truncated reward agreement is weak evidence.'}
for host,data in [('5070ti',left),('3060',right)]:
    def subset(condition,normalize):
        selected=copy.deepcopy(data)
        selected['cases']=[c for c in selected['cases']if condition(c)]
        for c in selected['cases']:normalize(c)
        return selected
    a=subset(lambda c:c['state']=='parent',lambda c:None)
    b=subset(lambda c:c['state']=='restored',lambda c:c.update(state='parent'))
    restored=compare(a,b)
    a=subset(lambda c:c['batch']==8,lambda c:None)
    b=subset(lambda c:c['batch']==32,lambda c:c.update(batch=8))
    batches=compare(a,b)
    result['withinGpu'][host]={'parentVsRestored':restored,'batch8Vs32':batches}
summary=[]
for policy in left['settings']['policies']:
    for batch in left['settings']['batches']:
        cases=[c for c in result['crossGpu']['cases']if c['policy']==policy and c['batch']==batch and c['state']!='restored']
        row={'policy':policy,'batch':batch,'rows':sum(c['rows']for c in cases),
             'tokenRowsDifferent':sum(c['tokenRowsDifferent']for c in cases),'rewardFlips':sum(c['rewardFlips']for c in cases)}
        summary.append(row);print(row)
result['summaryExcludingRestored']=summary
for host,d in result['withinGpu'].items():print(host,{k:(v['tokenRowsDifferent'],v['rewardFlips'])for k,v in d.items()})
out=root/'comparison-01.json'
with out.open('x')as f:json.dump(result,f,indent=2);f.write('\n')
