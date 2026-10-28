"""B22 full-weight projection: paired exact-output and captured timing controls, no adapters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

parser=argparse.ArgumentParser()
parser.add_argument('--gpu',action='store_true')
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
if args.out.exists():parser.error('Existing evidence')
if not args.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':parser.error('GPU opt-in required')
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference as oracle
from lookup_compressed import CompressedLookupKernels

report={'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__,'cuda':torch.version.cuda,'cases':[]}
baseline=IntegerCudaKernels('cuda',magnitude_bits=22)
variant=CompressedLookupKernels('cuda',magnitude_bits=22)
generator=torch.Generator().manual_seed(20261025)
cases=[(32,896,128),(32,896,896),(32,896,4864),(32,4864,896),
       (32,960,320),(32,960,960),(32,960,2560),(32,2560,960),
       (32,2048,256),(32,2048,2048),(32,2048,5632),(32,5632,2048),
       (128,896,896),(128,2048,5632)]
for rows,width,outputs in cases:
    cpu_x=torch.randn(rows,width,generator=generator)
    cpu_w=(torch.randn(outputs,width,generator=generator)*0.125).half()
    x,w=cpu_x.cuda(),cpu_w.cuda()
    graphs={};values={};flags={}
    for label,k in (('baseline',baseline),('lookup',variant)):
        k._begin_request((w,))
        flag=k.new_error_flag()
        k.linear_decode(x,w,error_flag=flag)
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):actual=k.linear_decode(x,w,error_flag=flag)
        graph.replay();torch.cuda.synchronize();k.raise_if_error(flag)
        graphs[label]=graph;values[label]=actual;flags[label]=flag
    assert torch.equal(values['baseline'].view(torch.int32),values['lookup'].view(torch.int32))
    expected=oracle.linear(cpu_x[:2],cpu_w[:3],magnitude_bits=22)
    assert torch.equal(values['lookup'][:2,:3].cpu().contiguous().view(torch.int32),expected.view(torch.int32))
    raw={'baseline':[],'lookup':[]}
    for label in ('baseline','lookup','lookup','baseline'):
        for _ in range(5):
            begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            begin.record()
            for _ in range(30):graphs[label].replay()
            end.record();end.synchronize()
            raw[label].append(begin.elapsed_time(end)/30)
    ratio=statistics.median(raw['baseline'])/statistics.median(raw['lookup'])
    report['cases'].append({'rows':rows,'width':width,'outputs':outputs,'eventMs':raw,'ratio':ratio})
    print(rows,width,outputs,round(ratio,4),flush=True)
    for k in (baseline,variant):k._end_request()
    del graphs,values,x,w
report['identities']={'baseline':baseline.identity(),'lookup':variant.identity()}
with args.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
