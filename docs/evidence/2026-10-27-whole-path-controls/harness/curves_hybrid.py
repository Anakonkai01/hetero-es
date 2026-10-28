"""Matched request-length curves and a CUDA timeline; no prefix reuse, EOS or arithmetic-equivalence claim."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
from types import SimpleNamespace

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--engine',choices=['mixed'],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
import torch
from transformers import AutoTokenizer
spec=importlib.util.spec_from_file_location('benchmark','runtime/scripts/benchmark_inference.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
args=SimpleNamespace(engine='vllm' if a.engine=='vllm' else 'strict-integer',model_path=path,max_new_tokens=128,max_context=512,memory_fraction=.35,enforce_eager=False,graph_max_bytes=6*1024**3,integer_bits=14 if a.engine=='b14' else 22,decode_ctas_per_sm=8,hf_chunk=0)
report={'status':'running','engine':a.engine,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'environment':{'python':platform.python_version()},'prefixCaching':False,'eosStopping':False,'hardwareQualified':False,'cases':[],'limits':'Finite parent inference controls; B14 and vendor arithmetic can change B22 tokens. No learning, quality or managed qualification.'}
engine,prompts,_=bench.load_engine(args,report)
from hybrid_precision import MixedDecoderGraph
engine=MixedDecoderGraph(engine.model,max_context=512,max_graph_bytes=6*1024**3)
report["mixedIdentity"]=engine.identity
tok=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
rows=[prompts[i%8] for i in range(32)]
report['promptTokenIds']=rows
runs={}
for n in (1,8,32,128):
    if a.engine=='vllm':
        from vllm import SamplingParams
        params=SamplingParams(temperature=0.0,max_tokens=n,ignore_eos=True,repetition_penalty=1.0)
        def run(selected,params=params):
            return [list(row.outputs[0].token_ids) for row in engine.generate([{'prompt_token_ids':ids} for ids in selected],params,use_tqdm=False)]
    else:
        run=bench.decoder_run(engine,pad=tok.pad_token_id or 0,tokens=n)
    result=bench.measure(run,rows,n,5,torch.cuda.synchronize)
    assert result['repeatTokensEqual']
    report['cases'].append({'outputTokens':n,**result})
    runs[n]=run
    print(a.engine,n,round(result['medianSeconds']*1000,2),'ms',round(result['tokensPerSecondTotal'],1),'token/s',flush=True)
with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CUDA]) as prof:
    runs[32](rows);torch.cuda.synchronize()
events=sorted((e.time_range.start,e.time_range.end,e.name) for e in prof.events() if e.device_type==torch.autograd.DeviceType.CUDA)
agg=defaultdict(lambda:[0,0.0])
for start,end,name in events:agg[name][0]+=1;agg[name][1]+=end-start
report['cudaProfile']={'kernelEvents':len(events),'spanUs':events[-1][1]-events[0][0],'busyUs':sum(e-b for b,e,_ in events),'byName':dict(agg)}
trace=a.out.with_suffix('.kernels.json')
with trace.open('x') as f:json.dump(events,f)
report['prefixEqualAcrossLengths']=all(short['tokens']==[r[:short['outputTokens']] for r in report['cases'][-1]['tokens']] for short in report['cases'])
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated()
report['status']='ok'
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print('CUDA span',round(report['cudaProfile']['spanUs']/1000,2),'ms','prefix equal',report['prefixEqualAcrossLengths'],flush=True)
