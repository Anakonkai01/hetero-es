"""Whole trained Qwen generation, changing only exact attention execution."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in/fresh output required')
import torch
from heteroes.eval.integer_decoder import IntegerDecoderGraph
from heteroes.v3.model import load,file_manifest
from warp_attention import WarpAttentionKernels

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
bench=module('benchmark','runtime/scripts/benchmark_inference.py')
probe=module('probe','runtime/scripts/probe_strict_backend.py')
path=Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen')
files=file_manifest(path);model,tokenizer=load(path,files,'cuda')
engines={name:IntegerDecoderGraph(model,magnitude_bits=22,max_context=512,max_graph_bytes=6*1024**3)
         for name in ('prior','score','full')}
attention={name:WarpAttentionKernels('cuda',mode=name)for name in ('score','full')}
for name,kernel in attention.items():engines[name].kernels.attention_packed=kernel.attention_packed
short=[tokenizer(s)['input_ids']for s in probe.PROMPTS]
workload=Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')
chat=json.loads(workload.read_text())['models']['qwen']['rows']
report={'gpu':torch.cuda.get_device_name(),'modelFiles':files,'cases':[],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'workloadSha256':hashlib.sha256(workload.read_bytes()).hexdigest()}
for label,tokens,selected in [('short32',32,[short[i%8]for i in range(32)]),
                             ('chat128',128,[r['tokenIds']for r in chat[:32]])]:
    runs={name:bench.decoder_run(e,pad=tokenizer.pad_token_id or 0,tokens=tokens)for name,e in engines.items()}
    expected={name:run(selected)for name,run in runs.items()}
    assert expected['prior']==expected['score']==expected['full']
    raw={name:[]for name in engines}
    for name in ('prior','score','full','full','score','prior'):
        for _ in range(5):
            start=time.perf_counter();actual=runs[name](selected);torch.cuda.synchronize()
            raw[name].append(time.perf_counter()-start)
            assert actual==expected['prior']
    summary={name:{'medianSeconds':statistics.median(times),'tokensPerSecond':32*tokens/statistics.median(times),
                   'speedRatio':statistics.median(raw['prior'])/statistics.median(times)}for name,times in raw.items()}
    report['cases'].append({'case':label,'batch':32,'outputTokens':tokens,'promptTokenIds':selected,
                            'tokens':expected['prior'],'wallSeconds':raw,'summary':summary})
    print(label,json.dumps(summary),flush=True)
report['identities']={name:e.kernel_identity()for name,e in engines.items()}
report['attentionIdentities']={name:k.identity()for name,k in attention.items()}
report['status']='ok'
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
