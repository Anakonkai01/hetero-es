"""Independent rescore of immutable historical parent receipts with frozen expected answers."""
import hashlib
import json
from pathlib import Path

from transformers import AutoTokenizer
from heteroes.eval.workload import extract_integer
from heteroes.study.evaluation import extract

root=Path('docs/evidence/2026-10-26-vllm-impact')
old=root.parent/'2026-10-24-vllm-probe'
rows=json.loads((root/'workload-01.json').read_text())['models']['qwen']['rows'][:208]
tokenizer=AutoTokenizer.from_pretrained('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen',local_files_only=True,trust_remote_code=False)
report={'inputs':{},'modes':{},'scope':'Historical parent-only receipts, no candidate/ranking result; 205 scorable rows'}
previous=json.loads((root/'legacy-impact-01.json').read_text())
for mode in ('default','invariant'):
    receipts={}
    for host in ('nhan','thao'):
        path=old/f'vllm-{host}-{mode}-large-01.json'
        receipts[host]=json.loads(path.read_text())
        assert receipts[host]['status']=='ok'
        assert receipts[host]['promptTokenIds']==[r['tokenIds'] for r in rows]
        report['inputs'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for layout in ('single','batched'):
        aa,bb=(receipts[h][layout] for h in ('nhan','thao'))
        assert len(aa)==len(bb)==208
        texts=[[tokenizer.decode(t,skip_special_tokens=True) for t in tokens] for tokens in (aa,bb)]
        for scorer,parser in (('last-integer',extract_integer),('answer-line-last-number',extract)):
            results=[]
            for i,row in enumerate(rows):
                if row['answer'] is None:continue
                target=int(row['answer']) if scorer=='last-integer' else row['answer']
                a,b=parser(texts[0][i]),parser(texts[1][i])
                results.append({'id':row['id'],'expected':target,'leftPrediction':a,'rightPrediction':b,
                                'leftReward':int(a==target),'rightReward':int(b==target),'tokensEqual':aa[i]==bb[i]})
            result={'scorable':len(results),'tokenDifferentAllPrompts':sum(a!=b for a,b in zip(aa,bb)),
                    'predictionsDifferent':sum(r['leftPrediction']!=r['rightPrediction'] for r in results),
                    'rewardFlips':sum(r['leftReward']!=r['rightReward'] for r in results),
                    'leftCorrect':sum(r['leftReward'] for r in results),'rightCorrect':sum(r['rightReward'] for r in results)}
            key=f'{mode}/{layout}/{scorer}'
            assert all(value==previous['modes'][key][name] for name,value in result.items())
            report['modes'][key]={**result,'differentCases':[r for r in results if not r['tokensEqual']]}
report['independentRescoreMatchesInitial']=True
with (root/'legacy-impact-02.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print('Independent rescore agrees for all 8 historical mode/layout/scorer combinations')
