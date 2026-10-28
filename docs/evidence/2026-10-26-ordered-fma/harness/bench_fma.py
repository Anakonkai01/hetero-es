"""Finite operator pilot; new arithmetic, no model or portability acceptance."""
import argparse
import json
import os
from pathlib import Path
import statistics

import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference
from fma_cuda import OrderedFmaKernels
from fma_reference import linear

p=argparse.ArgumentParser()
p.add_argument('--gpu',action='store_true')
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():
    p.error('GPU opt-in and fresh output required')
kernels={'b22':IntegerCudaKernels('cuda',magnitude_bits=22),'ordered_fma':OrderedFmaKernels('cuda')}
generator=torch.Generator().manual_seed(20261026)
report={'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'cases':[]}
for rows,width,outputs in [(32,896,128),(32,896,896),(32,896,4864),(32,4864,896),(32,2048,5632)]:
    cx=torch.randn(rows,width,generator=generator)
    cw=(torch.randn(outputs,width,generator=generator)*.125).half()
    x,w=cx.cuda(),cw.cuda()
    graphs={};values={};flags={};raw={name:[]for name in kernels}
    for name,k in kernels.items():
        if name=='b22':k._begin_request((w,))
        flag=k.new_error_flag()
        k.linear_decode(x,w,error_flag=flag)
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            for repeat in range(30):
                actual=k.linear_decode(x,w,error_flag=flag)
        graph.replay();torch.cuda.synchronize();k.raise_if_error(flag)
        graphs[name]=graph;values[name]=actual;flags[name]=flag
        expected=(integer_reference.linear(cx[:2],cw[:3],magnitude_bits=22)
                  if name=='b22' else linear(cx[:2],cw[:3]))
        assert torch.equal(actual[:2,:3].cpu().contiguous().view(torch.int32),expected.view(torch.int32))
    for name in ('b22','ordered_fma','ordered_fma','b22'):
        for _ in range(5):
            begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            begin.record();graphs[name].replay();end.record();end.synchronize()
            raw[name].append(begin.elapsed_time(end)/30)
    ratios={name:statistics.median(raw['b22'])/statistics.median(times)for name,times in raw.items()}
    report['cases'].append({'rows':rows,'width':width,'outputs':outputs,'eventMs':raw,'ratios':ratios})
    print(rows,width,outputs,ratios,flush=True)
    kernels['b22']._end_request()
    del graphs,values,flags,x,w
report['identities']={name:k.identity()for name,k in kernels.items()}
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
