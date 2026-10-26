"""Diagnostic external-event attribution, including nonprojection work; no throughput claim."""
import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in/fresh output required')
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.eval.fp16_decoder import Fp16DecoderGraph
from heteroes.eval.strict_decode_cuda import DecodeKernels
from heteroes.v3.model import load,file_manifest

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
bench=module('benchmark','runtime/scripts/benchmark_inference.py')
probe=module('probe','runtime/scripts/probe_strict_backend.py')
path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files=file_manifest(path);model,tokenizer=load(path,files,'cuda')
engines={'b22':IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3),
         'fp16':Fp16DecoderGraph(model,max_context=512,max_graph_bytes=6*1024**3)}
scopes={name:[]for name in engines}
current=None

def wrap(call,label,own=None):
    def invoke(*args,**kwargs):
        if not torch.cuda.is_current_stream_capturing():return call(*args,**kwargs)
        owner=own if own is not None else current
        begin=torch.cuda.Event(enable_timing=True,external=True)
        end=torch.cuda.Event(enable_timing=True,external=True)
        begin.record();result=call(*args,**kwargs);end.record()
        scopes[owner].append((label(*args),begin,end))
        return result
    return invoke

for own,engine in engines.items():
    names={id(m):n for n,m in model.named_modules()}
    def project_label(value,module,flag):
        n=names[id(module)]
        return 'head'if n=='lm_head'else ('down'if 'down_proj'in n else 'attn_out')
    def group_label(value,modules,flag):return 'qkv'if 'self_attn'in names[id(modules[0])]else 'gate_up'
    engine._decode_project=wrap(engine._decode_project,project_label,own)
    engine._decode_project_many=wrap(engine._decode_project_many,group_label,own)
    for name in ('rms_norm','add','silu_mul','rope','attention_packed'):
        setattr(engine.kernels,name,wrap(getattr(engine.kernels,name),lambda *args,n=name:n,own))
    engine._decode_core=wrap(engine._decode_core,lambda *args:'total',own)
for name in ('layout','store','greedy','publish'):
    setattr(DecodeKernels,name,wrap(getattr(DecodeKernels,name),lambda *args,n=name:'decode_'+n))

short=[tokenizer(text)['input_ids']for text in probe.PROMPTS]
workload=Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
chat=json.loads(workload.read_text())['models']['qwen']['rows']
report={'gpu':torch.cuda.get_device_name(),'modelFiles':files,
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'workloadSha256':hashlib.sha256(workload.read_bytes()).hexdigest(),'cases':[],
        'limits':'External nodes perturb scheduling. Final captured step only, not throughput. '
                 'Vendor projection arithmetic is a diagnostic control, not a strict solution.'}
for label,tokens,selected in [('short32',32,[short[i%8]for i in range(32)]),
                             ('chat128',128,[r['tokenIds']for r in chat[:32]])]:
    for own,engine in engines.items():
        current=own
        run=bench.decoder_run(engine,pad=tokenizer.pad_token_id or 0,tokens=tokens)
        expected=run(selected)
        records=[]
        for _ in range(10):
            assert run(selected)==expected
            torch.cuda.synchronize()
            sample=defaultdict(float)
            for name,begin,end in scopes[own]:sample[name]+=begin.elapsed_time(end)
            assert sum(v for k,v in sample.items()if k!='total')<sample['total']
            records.append(dict(sample))
        medians={name:statistics.median(r[name]for r in records)for name in records[0]}
        report['cases'].append({'case':label,'variant':own,'batch':32,'outputTokens':tokens,
                                'samplesMs':records,'medianMs':medians,'tokens':expected})
        print(label,own,json.dumps(medians),flush=True)
report['identities']={name:e.kernel_identity()for name,e in engines.items()}
report['status']='ok'
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
