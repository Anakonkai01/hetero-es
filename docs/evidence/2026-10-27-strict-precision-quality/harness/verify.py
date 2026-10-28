"""Reproduce finite quality metrics and verify per-precision cross-GPU output identity; no updates."""
import hashlib,importlib.util,json
from pathlib import Path
p=Path('docs/evidence/2026-10-27-strict-precision-quality');raw=p/'raw'
a=json.loads((raw/'quality-5070ti-01.json').read_text());b=json.loads((raw/'quality-3060-01.json').read_text())
assert a['status']==b['status']=='ok'
for key in ('modelFiles','schemaHash','parentSha256','workloadSha256','settings','noiseEngine','sigma'):assert a[key]==b[key],key
for x,y in zip(a['cases'],b['cases'],strict=True):
 assert x['label']==y['label'] and x['weightsSha256']==y['weightsSha256'] and x['restoreExact'] and y['restoreExact']
 for bits in ('22','14'):assert x['precisions'][bits]['outputs']==y['precisions'][bits]['outputs']
metrics=Path('docs/evidence/2026-10-26-vllm-impact/harness/impact_metrics.py')
spec=importlib.util.spec_from_file_location('impact',metrics);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
workload=Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json');rows=json.loads(workload.read_text())['models']['qwen']['rows']
assert hashlib.sha256(workload.read_bytes()).hexdigest()==a['workloadSha256']
old=json.loads((raw/'summary-3060-01.json').read_text());left=[];right=[];flips=0
for case,expected in zip(b['cases'],old['cases'],strict=True):
 impact=m.output_impact(rows,case['precisions']['22']['outputs'],case['precisions']['14']['outputs'])
 assert case['label']==expected['label'] and impact==expected['impact']
 if case['label']!='restored':flips+=impact['all']['rewardFlips']
 if case['candidateSeed'] is not None:left.append(impact['all']['leftReward']);right.append(impact['all']['rightReward'])
assert m.population_impact(left,right)==old['population']
result={'status':'ok','samePrecisionsAcrossGpus':True,'rowsPerPrecision':640,'metricsReproduced':True,'rewardFlipsExcludingRestoredParent':flips,'metricsSourceSha256':hashlib.sha256(metrics.read_bytes()).hexdigest(),'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'limits':'Finite inference outputs and hypothetical coefficients only. No learning or quality qualification.'}
with (raw/'verify-01.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
