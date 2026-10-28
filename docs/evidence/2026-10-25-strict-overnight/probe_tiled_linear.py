"""Finite scratch SIMT tile sweep, preserving the old arithmetic."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():
    p.error('Need GPU acceptance and fresh receipt')
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels, _check
from heteroes.eval import reference_ops as ops
from tiled_linear import prepare

report={'status':'running','gpu':torch.cuda.get_device_name(),'hardwareQualified':False,'cases':[],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('tiled_linear.py').read_bytes()).hexdigest(),
        'limits':'Synthetic finite projection shapes. CUDA Graph repeated raw launches isolate kernel time; not full decoder.'}
try:
    for width,outputs in ((768,4096),(1024,32768),(2048,11008),(4096,4096)):
        gen=torch.Generator().manual_seed(width)
        w=(torch.randn(outputs,width,generator=gen)*.02).half().cuda()
        x=torch.randn(32,width,generator=gen).cuda()
        base=StrictCudaKernels('cuda'); expected=base.linear(x,w)
        oracle=ops.linear(x[:3].cpu(),w[:3].cpu())
        assert torch.equal(expected[:3,:3].cpu().contiguous().view(torch.int32),oracle.view(torch.int32))
        for per,tile,groups in ((4,8,4),(8,8,4),(8,16,4),(8,32,4),(16,8,2),(16,16,2)):
            kernels,launch,out,parts,flag=prepare(x,w,tile=tile,per=per,groups=groups)
            launch();kernels.raise_if_error(flag)
            assert torch.equal(out.view(torch.int32),expected.view(torch.int32)), (width,per,tile)
            g=torch.cuda.CUDAGraph()
            with torch.cuda.graph(g):
                for _ in range(20): launch()
            ms=[]
            for _ in range(3):
                start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                start.record();g.replay();end.record();end.synchronize()
                ms.append(start.elapsed_time(end)/20)
            kernels.raise_if_error(flag)
            case={'width':width,'outputs':outputs,'rows':32,'per':per,'rowTile':tile,'groups':groups,
                  'eventMs':ms,'medianEventMs':statistics.median(ms),'workspaceBytes':parts.numel()*parts.element_size(),
                  'bitsEqual':True,'identity':kernels.identity()}
            report['cases'].append(case)
            print(json.dumps({k:case[k] for k in ('width','per','rowTile','medianEventMs','workspaceBytes')}),flush=True)
            del g,launch,out,parts,kernels
        del x,w,expected,base
    report['status']='ok'
except Exception as exc:
    report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}))
raise SystemExit(report['status']!='ok')
