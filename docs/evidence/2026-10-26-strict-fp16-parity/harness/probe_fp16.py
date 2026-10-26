"""Finite same-candidate GEMM-FP16 survey across GPU/batch/accumulation policies; no learning."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true')
p.add_argument('--model-path',type=Path,required=True);p.add_argument('--workload',type=Path,required=True)
p.add_argument('--out',type=Path,required=True);p.add_argument('--rows',type=int,default=32)
p.add_argument('--tokens',type=int,default=128);p.add_argument('--seeds',nargs='+',type=int,default=[7001])
p.add_argument('--batches',nargs='+',type=int,default=[8,32]);p.add_argument('--policies',nargs='+',choices=('default','fp32_acc'),default=['default','fp32_acc'])
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in/fresh output required')
import torch
import transformers
from heteroes.canonical import canonical_json_hash
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_,take_snapshot
from heteroes.eval.candidate import model_weights_sha256
from heteroes.eval.fp16_decoder import Fp16DecoderGraph
from heteroes.model.schema import build_parameter_schema
from heteroes.noise.contracts import ENGINE_V2
from heteroes.study.evaluation import extract
from heteroes.v3.model import load,file_manifest

def flags():
    return {'allowFP16ReducedReduction':torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction,
            'allowFP16Accumulation':torch.backends.cuda.matmul.allow_fp16_accumulation,
            'allowTF32':torch.backends.cuda.matmul.allow_tf32}
original=flags()
report={'status':'running','sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'workloadSha256':hashlib.sha256(a.workload.read_bytes()).hexdigest(),
        'settings':{'rows':a.rows,'tokens':a.tokens,'seeds':a.seeds,'batches':a.batches,'policies':a.policies,'sigma':.001,'eosStopping':True},
        'environment':{'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'transformers':transformers.__version__,
                       'cuda':torch.version.cuda,'platform':platform.platform()},'cases':[],
        'limits':'Finite standalone D2 survey, not steady performance, universal vendor equality or learning. '
                 'Short output budget may truncate answers; reward agreement is weak evidence.'}
started=time.perf_counter();snapshot=None;engine=None
try:
    files=file_manifest(a.model_path);model,tokenizer=load(a.model_path,files,'cuda')
    engine=Fp16DecoderGraph(model,max_context=1024,max_graph_bytes=6*1024**3)
    schema=build_parameter_schema(model);snapshot=take_snapshot(model,schema);parent=model_weights_sha256(model,schema)
    rows=json.loads(a.workload.read_text())['models']['qwen']['rows'][:a.rows]
    if len(rows)!=a.rows or max(len(r['tokenIds'])for r in rows)+a.tokens>1024:raise ValueError('Invalid finite workload size')
    report.update(modelFiles=files,modelFilesHash=canonical_json_hash(files),schemaHash=schema.hash,parentSha256=parent,
                  promptTokenIds=[r['tokenIds']for r in rows],backendIdentity=engine.identity)
    eos=engine.generation_config.eos_token_id
    eos=[]if eos is None else [eos]if type(eos)is int else list(eos)
    descriptors=[('parent',None,0.)]+[(f'{seed}{sign:+d}',seed,sign*.001)for seed in a.seeds for sign in (1,-1)]+[('restored',None,0.)]
    for state,seed,sigma in descriptors:
        restore_from_snapshot_(model,schema,snapshot)
        if seed is not None:perturb_model_(model,schema,seed,sigma,engine=ENGINE_V2)
        weight_hash=model_weights_sha256(model,schema)
        for policy in a.policies:
            engine.release_graph()
            torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=original['allowFP16ReducedReduction']if policy=='default'else False
            torch.backends.cuda.matmul.allow_fp16_accumulation=original['allowFP16Accumulation']if policy=='default'else False
            for batch in a.batches:
                case={'state':state,'seed':seed,'sigma':sigma,'policy':policy,'batch':batch,'flags':flags(),
                      'weightsSha256':weight_hash,'outputs':[]}
                begin=time.perf_counter()
                for offset in range(0,len(rows),batch):
                    subset=rows[offset:offset+batch];width=max(len(r['tokenIds'])for r in subset)
                    ids=torch.full((len(subset),width),tokenizer.pad_token_id or 0,dtype=torch.long,device='cuda')
                    mask=torch.zeros_like(ids)
                    for i,row in enumerate(subset):
                        ids[i,-len(row['tokenIds']):]=torch.tensor(row['tokenIds'],dtype=torch.long,device='cuda')
                        mask[i,-len(row['tokenIds']):]=1
                    output=engine.generate(ids,attention_mask=mask,max_new_tokens=a.tokens,eos_token_id=eos,
                                           pad_token_id=tokenizer.pad_token_id or 0,repetition_penalty=1.)
                    for row,tokens in zip(subset,output[:,width:].tolist(),strict=True):
                        stop=next((i for i,t in enumerate(tokens)if t in eos),None)
                        finished=stop is not None
                        if finished:tokens=tokens[:stop+1]
                        text=tokenizer.decode(tokens,skip_special_tokens=True)
                        prediction=extract(text)
                        case['outputs'].append({'id':row['id'],'tokens':tokens,'text':text,'finished':finished,
                                                'prediction':prediction,'reward':float(prediction==str(row['answer']))})
                torch.cuda.synchronize();case['secondsIncludingCapture']=time.perf_counter()-begin
                report['cases'].append(case)
                print(state,policy,batch,'rows',len(case['outputs']),'seconds',round(case['secondsIncludingCapture'],3),flush=True)
        if model_weights_sha256(model,schema)!=weight_hash:raise ValueError('Inference changed weights')
    report['kernelIdentity']=engine.kernel_identity();report['status']='ok'
except Exception as error:
    report.update(status='error',errorType=type(error).__name__,error=str(error)[:2000])
finally:
    if snapshot is not None:
        restore_from_snapshot_(model,schema,snapshot)
        report['finalRestoreExact']=model_weights_sha256(model,schema)==parent
        if not report['finalRestoreExact']:report['status']='error'
    torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=original['allowFP16ReducedReduction']
    torch.backends.cuda.matmul.allow_fp16_accumulation=original['allowFP16Accumulation']
    report['wallSeconds']=time.perf_counter()-started
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(report['status'],a.out,flush=True)
raise SystemExit(0 if report['status']=='ok'else 1)
