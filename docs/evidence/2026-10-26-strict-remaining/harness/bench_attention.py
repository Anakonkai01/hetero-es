"""Bounded attention operator pilot: same operands and arithmetic, graph event times."""
import argparse
import json
import os
from pathlib import Path
import statistics
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from warp_attention import WarpAttentionKernels

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in/fresh output required')
kernels={'prior':StrictCudaKernels('cuda'),'score':WarpAttentionKernels('cuda',mode='score'),
         'full':WarpAttentionKernels('cuda',mode='full')}
rng=torch.Generator().manual_seed(20261026)
report={'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'cases':[]}
for label,length,context in [('decode32',1,32),('decode128',1,128),('decode256',1,256),('decode512',1,512),
                             ('prefill8',8,8),('prefill128',128,128)]:
    spans=[(length,context,context-length)]*32
    q=(torch.randn((14,32*length,64),generator=rng)*.125).cuda()
    k=(torch.randn((2,32*context,64),generator=rng)*.125).cuda()
    v=torch.randn((2,32*context,64),generator=rng).cuda()
    graphs={};values={};flags={};layouts={};raw={name:[]for name in kernels}
    for name,kernel in kernels.items():
        layout=kernel.attention_layout(spans);flag=kernel.new_error_flag()
        kernel.attention_packed(q,k,v,layout,7,.125,error_flag=flag)
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            for _ in range(30):actual=kernel.attention_packed(q,k,v,layout,7,.125,error_flag=flag)
        graph.replay();torch.cuda.synchronize();kernel.raise_if_error(flag)
        graphs[name]=graph;values[name]=actual;flags[name]=flag;layouts[name]=layout
    assert torch.equal(values['prior'].view(torch.int32),values['score'].view(torch.int32))
    assert torch.equal(values['prior'].view(torch.int32),values['full'].view(torch.int32))
    for name in ('prior','score','full','full','score','prior'):
        for _ in range(5):
            begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            begin.record();graphs[name].replay();end.record();end.synchronize()
            raw[name].append(begin.elapsed_time(end)/30)
    ratios={name:statistics.median(raw['prior'])/statistics.median(times)for name,times in raw.items()}
    report['cases'].append({'label':label,'length':length,'context':context,'batch':32,'heads':14,
                            'kvHeads':2,'headDim':64,'eventMs':raw,'ratios':ratios})
    print(label,ratios,flush=True)
    del graphs,values,flags,layouts,q,k,v
report['identities']={name:k.identity()for name,k in kernels.items()}
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
