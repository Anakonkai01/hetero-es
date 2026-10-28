"""Pair verified candidates; quantify score, ranking and hypothetical update sensitivity."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from heteroes.noise.contracts import ChunkNoiseAddress, DEFAULT_CHUNK_ELEMENTS, ENGINE_V2
from heteroes.noise.engine_v2 import generate_chunk_noise
from impact_metrics import output_impact, population_impact

p=argparse.ArgumentParser()
p.add_argument('--left',type=Path,required=True)
p.add_argument('--right',type=Path,required=True)
p.add_argument('--workload',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists():p.error('Existing evidence')
left,right=(json.loads(path.read_text()) for path in (a.left,a.right))
assert left['status']==right['status']=='ok'
for key in ('model','modelFiles','workloadSha256','settings','sourceSha256'):
    assert left[key]==right[key],key
for key in ('schemaHash','parentSha256','allViewStoragesOwnedByVllm'):
    assert left['preparation'][key]==right['preparation'][key],key
assert left['preparation']['allViewStoragesOwnedByVllm']
assert left['finalRestore']['parentRestored'] and right['finalRestore']['parentRestored']
assert hashlib.sha256(a.workload.read_bytes()).hexdigest()==left['workloadSha256']
workload=json.loads(a.workload.read_text())
rows=workload['models'][left['model']]['rows']
assert len(left['cases'])==len(right['cases'])==10
assert left['cases'][0]['label']==right['cases'][0]['label']=='parent'
assert left['cases'][-1]['label']==right['cases'][-1]['label']=='restored'
report={'model':left['model'],'sourceCommit':'b360bdb5','inputs':{str(path):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (a.left,a.right,a.workload)},'candidateWeightsAndPromptIdsEqual':True,
        'cases':[],'populations':{},'sameHostRestoreInference':{},
        'limitations':'Finite first-64 GSM8k plus historical prompts. Mixed assignments and coefficient/sample '
                      'directions are offline counterfactuals; no ES update or learning. Sample is one canonical chunk.'}
for ca,cb in zip(left['cases'],right['cases'],strict=True):
    for key in ('label','candidateSeed','sign','weightsSha256'):
        assert ca[key]==cb[key],(ca['label'],key)
    impact=output_impact(rows,ca['outputs'],cb['outputs'])
    report['cases'].append({'label':ca['label'],'groups':impact})
for host,data in (('5070ti',left),('3060',right)):
    assert data['cases'][0]['weightsSha256']==data['cases'][-1]['weightsSha256']==data['preparation']['parentSha256']
    assert all(c['weightsSha256']!=data['preparation']['parentSha256'] for c in data['cases'][1:-1])
    report['sameHostRestoreInference'][host]=output_impact(rows,data['cases'][0]['outputs'],data['cases'][-1]['outputs'])
seeds=left['settings']['candidateSeeds']
assert [(c['candidateSeed'],c['sign']) for c in left['cases'][1:-1]]==[(s,sign) for s in seeds for sign in (1,-1)]
sample=[];fingerprints={}
for seed in seeds:
    eps=generate_chunk_noise(ChunkNoiseAddress(seed,left['preparation']['schemaHash'],0,0,DEFAULT_CHUNK_ELEMENTS),DEFAULT_CHUNK_ELEMENTS)
    fingerprints[str(seed)]=hashlib.sha256(eps.tobytes()).hexdigest()
    sample.append(eps.astype(np.float64))
sample=np.stack(sample)
gram=sample @ sample.T / sample.shape[1]
report['directionSample']={'engine':ENGINE_V2,'schemaHash':left['preparation']['schemaHash'],'parameterIndex':0,
                           'chunkIndex':0,'chunkElements':DEFAULT_CHUNK_ELEMENTS,'samplesPerSeed':sample.shape[1],
                           'noiseSha256':fingerprints,'gram':gram.tolist()}
for group in ('all','historical','gsm8k-first64'):
    ac=[c['groups'][group]['leftReward'] for c in report['cases'][1:-1]]
    bc=[c['groups'][group]['rightReward'] for c in report['cases'][1:-1]]
    report['populations'][group]=population_impact(ac,bc,gram)
a.out.parent.mkdir(parents=True,exist_ok=True)
with a.out.open('x') as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
for group in ('all','historical','gsm8k-first64'):
    cases=[c['groups'][group] for c in report['cases'][:-1]]
    population=report['populations'][group]
    print(left['model'],group,'rows',sum(c['rows'] for c in cases),'token-diff',sum(c['tokenRowsDifferent'] for c in cases),
          'reward-flips',sum(c['rewardFlips'] for c in cases),'scorable',sum(c['scorable'] for c in cases),
          'max candidate reward delta pp',round(100*population['maxAbsRewardDelta'],4),
          'strict rank inversions',population['strictPairInversions'],'tie changes',population['tieStatusChanges'])
    print('means',population['leftRewards'],population['rightRewards'])
    for rule,metrics in population['rules'].items():
        print(rule,'all-other cosine',metrics['sampledCanonicalDirectionCosine'],'worst-mixed cosine',metrics['minimumSampledDirectionCosine'],
              'mixed best changes',metrics['mixedAssignmentsChangingBestSet'])
