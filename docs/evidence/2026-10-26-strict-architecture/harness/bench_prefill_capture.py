"""Whole-path projection controls and CPU critical-path regions, one primary FP16 model."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

p=argparse.ArgumentParser()
p.add_argument('--gpu',action='store_true')
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():
    p.error('GPU opt-in and fresh output required')
import torch
import torch.nn.functional as F
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.fp16_decoder import Fp16DecoderGraph
from prefill_capture import PrefillIntegerGraph,PrefillFp16Graph
from heteroes.eval.strict_decoder_graph import StrictDecoderGraph,_DecodeSession
from heteroes.v3.model import load,file_manifest

class SeparateFp16Graph(StrictDecoderGraph):
    def _project(self,value,module,flag):
        return F.linear(value.half(),module.weight,getattr(module,'bias',None)).float()
    def _project_many(self,value,modules,flag):
        x=value.half()
        return tuple(F.linear(x,m.weight,getattr(m,'bias',None)).float()for m in modules)

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
bench=module('benchmark','runtime/scripts/benchmark_inference.py')
probe=module('probe','runtime/scripts/probe_strict_backend.py')
model_path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files=file_manifest(model_path)
model,tokenizer=load(model_path,files,'cuda')
engines={'b22':IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3),
         'b22_prefill':PrefillIntegerGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3),
         'fp16_prefill':PrefillFp16Graph(model,max_context=512,max_graph_bytes=6*1024**3)}
short=[tokenizer(s)['input_ids']for s in probe.PROMPTS]
workload_path=Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
chat=json.loads(workload_path.read_text())['models']['qwen']['rows']
active=False
regions=defaultdict(float)
counts=defaultdict(int)

def instrument(call,name):
    def invoke(*args,**kwargs):
        if not active:return call(*args,**kwargs)
        start=time.perf_counter()
        try:return call(*args,**kwargs)
        finally:
            regions[name]+=time.perf_counter()-start
            counts[name]+=1
    return invoke

for engine in engines.values():
    for name in ('forward_batch','_generation_begin','_generation_end'):
        setattr(engine,name,instrument(getattr(engine,name),name))
for name in ('read','select','prefix','clear','capture'):
    setattr(_DecodeSession,name,instrument(getattr(_DecodeSession,name),name))
report={'status':'running','sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'gpu':torch.cuda.get_device_name(),'modelFiles':files,'workloadSha256':hashlib.sha256(workload_path.read_bytes()).hexdigest(),
        'matmulFlags':{'allowTF32':torch.backends.cuda.matmul.allow_tf32,
                      'allowFP16ReducedPrecisionReduction':torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction},
        'cases':[],'limits':'Vendor controls have different arithmetic and are not strict solutions. '
        'Wall regions include GPU waiting and cannot be interpreted as exclusive GPU kernel time. '
        'Warmup/capture excluded. No perturbation, learning or managed operation.'}
torch.cuda.reset_peak_memory_stats()
for label,tokens,selected in (
    ('short32',32,[short[i%8]for i in range(32)]),
    ('chat128',128,[r['tokenIds']for r in chat[:32]]),
):
    runs={name:bench.decoder_run(e,pad=tokenizer.pad_token_id or 0,tokens=tokens)for name,e in engines.items()}
    expected={name:run(selected)for name,run in runs.items()}
    assert expected['b22']==expected['b22_prefill']
    captures={name:getattr(e,'prefill_capture_count',None)for name,e in engines.items()}
    records=[]
    for name in ('b22','b22_prefill','fp16_prefill','fp16_prefill','b22_prefill','b22'):
        for repeat in range(5):
            regions.clear();counts.clear();active=True
            start=time.perf_counter()
            actual=runs[name](selected)
            torch.cuda.synchronize()
            elapsed=time.perf_counter()-start
            active=False
            assert actual==expected[name] and len(actual)==32 and all(len(r)==tokens for r in actual)
            assert sum(regions.values())<elapsed
            assert {name:getattr(e,'prefill_capture_count',None)for name,e in engines.items()}==captures
            records.append({'variant':name,'seconds':elapsed,'regions':dict(regions),'counts':dict(counts)})
    summary={}
    for name in engines:
        own=[r for r in records if r['variant']==name]
        summary[name]={'tokensPerSecond':32*tokens/statistics.median(r['seconds']for r in own),
                       'medianSeconds':statistics.median(r['seconds']for r in own),
                       'medianRegions':{key:statistics.median(r['regions'].get(key,0)for r in own)for key in regions}}
    report['cases'].append({'label':label,'batch':32,'outputTokens':tokens,'promptTokenIds':selected,
                            'tokensByVariant':expected,'records':records,'summary':summary,'prefillCaptures':captures})
    print(label,json.dumps(summary),flush=True)
report['kernelIdentities']={name:e.kernel_identity()for name,e in engines.items()}
assert report['kernelIdentities']['b22']['weightLoadEffective']=='prefetch2'
report['backendIdentities']={name:e.identity for name,e in engines.items()}
assert all(not bool(t.any())for name,e in engines.items()if name!='b22'for t in e.prefill_request_buffers())
report['peakAllocatedBytes']=torch.cuda.max_memory_allocated()
report['status']='ok'
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
