"""Captured single-weight-set mixed-precision operator measurements; no model quality claim."""
import argparse
import json
import os
from pathlib import Path
import statistics

import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from bounded_cuda import BoundedKernels
from half2_cuda import Half2BoundedKernels
from vendor_bmm import VendorBoundedKernels
from bounded_reference import linear
from heteroes.eval import integer_reference

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh output required')
torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=False
torch.backends.cuda.matmul.allow_fp16_accumulation=False
kernels={'a22w22':IntegerCudaKernels('cuda',magnitude_bits=22),
         'a8w8':Half2BoundedKernels('cuda',activation_bits=8,weight_bits=8),
         'vendor8':VendorBoundedKernels('cuda',activation_bits=8,weight_bits=8)}
generator=torch.Generator().manual_seed(20261026)
report={'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'cases':[]}
shapes=[(32,896,128),(32,896,896),(32,896,4864),(32,4864,896),(32,2048,5632)]
for rows,width,outputs in shapes:
    cx=torch.randn(rows,width,generator=generator)
    cw=(torch.randn(outputs,width,generator=generator)*.125).half()
    x,w=cx.cuda(),cw.cuda();graphs={};values={};raw={name:[] for name in kernels}
    for name,k in kernels.items():
        k._begin_request((w,));flag=k.new_error_flag()
        k.linear_decode(x,w,error_flag=flag)
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            for body_repeat in range(30):
                actual=k.linear_decode(x,w,error_flag=flag)
        graph.replay();torch.cuda.synchronize();k.raise_if_error(flag)
        graphs[name]=graph;values[name]=actual
        expected=integer_reference.linear(cx[:2],cw[:3],magnitude_bits=22) if name=='a22w22' else linear(cx[:2],cw[:3],activation_bits=8,weight_bits=8)
        assert torch.equal(actual[:2,:3].cpu().contiguous().view(torch.int32),expected.view(torch.int32))
    for name in ('a22w22','a8w8','vendor8','vendor8','a8w8','a22w22'):
        for _ in range(5):
            begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            begin.record()
            graphs[name].replay()
            end.record();end.synchronize()
            raw[name].append(begin.elapsed_time(end)/30)
    ratios={name:statistics.median(raw['a22w22'])/statistics.median(times) for name,times in raw.items()}
    report['cases'].append({'rows':rows,'width':width,'outputs':outputs,'eventMs':raw,'ratios':ratios})
    print(rows,width,outputs,ratios,flush=True)
    for k in kernels.values():k._end_request()
    del graphs,values,x,w
report['identities']={name:k.identity() for name,k in kernels.items()}
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
