"""Verify frozen bounded-head receipts and compare canonical outputs; summarize matched ABAB timing."""
import json
from pathlib import Path
import statistics
root=Path('docs/evidence/2026-10-27-strict-combined-acceptance/raw')
prior=Path('docs/evidence/2026-10-27-strict-bounded-lm-head/raw')

def read(p):return json.loads(p.read_text())
def canonical(p):
 d=read(p);assert d['status']=='ok',p
 assert all(c['tileEqualsStream'] and c['restoreExact'] for c in d['cases']),p
 result=[{k:c[k] for k in ('state','weightsSha256','results')} for c in d['cases']]
 if 'eosCheck' in d:
  e=d['eosCheck'];assert e['equal'] and e['captured']==e['uncaptured'],p
  result.append(e)
 return result

summary={'commit':'0eb86cb948878fe430049882b80b3a5ad74730ba','hardwareQualified':False,'canonicalParity':{},'timings':{}}
for model in ('qwen','smol','tiny'):
 local=root/f'{model}-parity-5070ti-01.json';remote=root/'3060-wsl-01'/f'{model}-parity-3060-01.json'
 a,b=canonical(local),canonical(remote);assert a==b,model
 assert a==canonical(prior/f'{model}-parity-5070ti-01.json'),model
 assert a==canonical(prior/'3060-wsl-01'/f'{model}-parity-3060-01.json'),model
 summary['canonicalParity'][model]={'5070tiEquals3060Wsl':True,'equalsPrecedingBoundedHead':True}
native=root/'3060-native-01';receipt=read(native/'codex-combined-native-run-01.json')
assert receipt['status']=='ok' and receipt['pytestExitCode']==0 and receipt['trainedQwenParityExitCode']==0
assert receipt['sourceManifestEqual'] and receipt['sourceManifestUnchangedAfter'] and receipt['commit']==summary['commit']
assert receipt['sourceArchiveSha256']==(root/'remote-source-01.sha256').read_text().split()[0]
assert canonical(native/'codex-combined-01/qwen-parity-native-01.json')==canonical(root/'qwen-parity-5070ti-01.json')
summary['canonicalParity']['qwen']['nativeEqualsBothLinuxHosts']=True
summary['nativeManifestVerified']=True
for host,path,pattern in [('5070ti',root,'single-qwen-{v}-5070ti-01?.json'),('3060-wsl',root/'3060-wsl-01','single-qwen-{v}-3060-01?.json'),('3060-native',native/'codex-combined-01','single-qwen-{v}-native-*.json')]:
 files={v:sorted(path.glob(pattern.format(v=v))) for v in ('base','new')}
 assert all(len(x)==2 for x in files.values()),(host,files)
 data={v:[read(p) for p in paths] for v,paths in files.items()}
 summary['timings'][host]={}
 for label in ('short32','chat128'):
  entries={v:[next(c for c in d['cases'] if c['case']==label) for d in ds] for v,ds in data.items()}
  assert len({c['tokensSha256'] for cs in entries.values() for c in cs})==1
  base,new=[statistics.mean(c['medianTokensPerSecond'] for c in entries[v]) for v in ('base','new')]
  summary['timings'][host][label]={'baseMeanOfRoundMedians':base,'newMeanOfRoundMedians':new,'gainPercent':100*(new/base-1)}
summary['limits']='Finite fixtures/canonical candidates; SM80/89/90 code generation only. No learning, managed/native-installer qualification or near-80%-vLLM acceptance.'
out=root/'summary-01.json'
with out.open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
print(json.dumps(summary,indent=2))
