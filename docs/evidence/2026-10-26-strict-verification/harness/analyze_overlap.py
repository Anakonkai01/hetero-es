"""Finite offline suffix-proposal diagnostic; never a measured decoding speedup."""
import hashlib
import json
from pathlib import Path
from overlap import simulate

sources=[('strict-short',Path('docs/evidence/2026-10-26-strict-prefetch/raw/qwen-candidates-5070ti-02.json')),
         ('vendor-chat-control',Path('docs/evidence/2026-10-26-vllm-impact/raw/qwen-chat-5070ti-01.json'))]
report={'limits':'Offline simulation with recorded target tokens as verifier. No new model inference, '
                 'GPU throughput, candidate quality, arithmetic proof or speculative decoder acceptance. '
                 'Chat traces come from vendor control, not own strict. Excludes first token/prefill. '
                 'Query expansion counts hypothetical row positions, not FLOPs or time.','sources':[]}
for label,path in sources:
    data=json.loads(path.read_text())
    if label=='strict-short':
        cases=[(c['state'],c['engines']['selected']['tokens'])for c in data['cases']if c['state']!='restored']
    else:cases=[(c['label'],[r['tokens']for r in c['outputs']])for c in data['cases']if c['label']!='restored']
    prior=[cases[0][1]];records=[]
    for name,targets in cases[1:]:
        for bank in ('parent','previous'):
            for block in (2,4,8):
                results=[]
                for row,target in enumerate(targets):
                    selected=prior[:1]if bank=='parent'else prior
                    results.append(simulate([case[row]for case in selected],target,block=block))
                rounds=sum(r['rounds']for r in results);positions=sum(r['verifiedPositions']for r in results)
                tokens=sum(len(t)-1 for t in targets)
                result={'case':name,'bank':bank,'block':block,'tokensAfterFirst':tokens,'rounds':rounds,
                        'verifiedPositions':positions,'tokensPerRound':tokens/rounds,
                        'queryExpansion':positions/tokens}
                records.append(result)
        prior.append(targets)
    own={'label':label,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cases':records}
    report['sources'].append(own)
    for bank in ('parent','previous'):
        for block in (2,4,8):
            selected=[r for r in records if r['bank']==bank and r['block']==block]
            tokens=sum(r['tokensAfterFirst']for r in selected)
            rounds=sum(r['rounds']for r in selected);positions=sum(r['verifiedPositions']for r in selected)
            print(label,bank,block,round(tokens/rounds,3),'tokens/round',round(positions/tokens,3),'query expansion')
out=Path('docs/evidence/2026-10-26-strict-verification/suffix-overlap-01.json')
with out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
