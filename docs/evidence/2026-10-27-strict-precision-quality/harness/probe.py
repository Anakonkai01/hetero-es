"""Finite B22/B14 candidate comparison: shared live model, canonical perturbations, exact restore, no update."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--model-path',type=Path,required=True);p.add_argument('--workload',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
import torch
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_,take_snapshot
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_V2
from heteroes.v3.model import load,file_manifest

rows=json.loads(a.workload.read_text())['models']['qwen']['rows']
model,tok=load(a.model_path,file_manifest(a.model_path),'cuda')
schema=build_parameter_schema(model);snapshot=take_snapshot(model,schema);parent=model_weights_sha256(model,schema)
ends=sorted({tok.eos_token_id,*([model.generation_config.eos_token_id] if isinstance(model.generation_config.eos_token_id,int) else model.generation_config.eos_token_id or [])}-{None})
engines={str(bits):IntegerDecoderGraph(model,magnitude_bits=bits,max_context=1024,max_graph_bytes=6*1024**3) for bits in (22,14)}
report={'status':'running','hardwareQualified':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'modelFiles':file_manifest(a.model_path),'schemaHash':schema.hash,'parentSha256':parent,'workloadSha256':hashlib.sha256(a.workload.read_bytes()).hexdigest(),'noiseEngine':ENGINE_V2,'sigma':1e-3,'settings':{'rows':len(rows),'batch':32,'maxContext':1024,'maxNewTokens':512,'eosTokenIds':ends,'prefixCaching':False},'environment':{'gpu':torch.cuda.get_device_name(),'cc':list(torch.cuda.get_device_capability()),'torch':torch.__version__,'cuda':torch.version.cuda,'python':platform.python_version(),'platform':platform.platform()},'identities':{b:e.identity for b,e in engines.items()},'cases':[],'limits':'Finite parent/canonical-pair arithmetic comparison; no ES update, learning claim, historical recipe change or universal quality acceptance.'}
started=time.perf_counter();torch.cuda.reset_peak_memory_stats()
try:
    descriptors=[('parent',None,0)]+[(f'{seed}{sign:+d}',seed,sign) for seed in (7001,7002,7003,7004) for sign in (1,-1)]+[('restored',None,0)]
    for label,seed,sign in descriptors:
        case={'label':label,'candidateSeed':seed,'sign':sign,'precisions':{}};report['cases'].append(case)
        try:
            if sign:perturb_model_(model,schema,seed,sign*1e-3,engine=ENGINE_V2)
            case['weightsSha256']=model_weights_sha256(model,schema)
            for bits,engine in engines.items():
                outputs=[];begin=time.perf_counter()
                for offset in range(0,len(rows),32):
                    subset=rows[offset:offset+32];width=max(len(r['tokenIds']) for r in subset)
                    assert width+512<=1024
                    ids=torch.full((len(subset),width),tok.pad_token_id or 0,dtype=torch.long,device='cuda');mask=torch.zeros_like(ids)
                    for i,row in enumerate(subset):
                        ids[i,-len(row['tokenIds']):]=torch.tensor(row['tokenIds'],device='cuda');mask[i,-len(row['tokenIds']):]=1
                    result=engine.generate(ids,attention_mask=mask,max_new_tokens=512,eos_token_id=ends,pad_token_id=tok.pad_token_id or 0,repetition_penalty=1.0)[:,width:].tolist()
                    for row,tokens in zip(subset,result,strict=True):
                        stop=next((i for i,t in enumerate(tokens) if t in ends),None)
                        if stop is not None:tokens=tokens[:stop+1]
                        outputs.append({'id':row['id'],'tokens':tokens,'text':tok.decode(tokens,skip_special_tokens=True),'finishReason':'stop' if stop is not None else 'length','stopReason':tokens[-1] if stop is not None else None})
                    print(label,bits,offset+len(subset),'of',len(rows),flush=True)
                engine.release_graph()
                case['precisions'][bits]={'outputs':outputs,'secondsIncludingFirstCapture':time.perf_counter()-begin}
        finally:
            for engine in engines.values():engine.release_graph()
            restore_from_snapshot_(model,schema,snapshot)
            case['restoreExact']=model_weights_sha256(model,schema)==parent
            assert case['restoreExact']
    assert report['cases'][0]['precisions']['22']['outputs']==report['cases'][-1]['precisions']['22']['outputs']
    assert report['cases'][0]['precisions']['14']['outputs']==report['cases'][-1]['precisions']['14']['outputs']
    report['status']='ok'
except Exception as error:
    report.update(status='error',errorType=type(error).__name__,error=str(error)[:2000])
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated();report['wallSeconds']=time.perf_counter()-started
with a.out.open('x') as f:json.dump(report,f,indent=1);f.write('\n')
print(json.dumps({'status':report['status'],'wallSeconds':report['wallSeconds']}),flush=True)
raise SystemExit(report['status']!='ok')
