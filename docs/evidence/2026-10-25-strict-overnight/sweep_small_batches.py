"""Independent small-batch decomposition sweep, with the unchanged integer-FTZ/tree arithmetic."""
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
    p.error('Need explicit GPU acceptance and a fresh receipt')
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels,LinearPlan
from heteroes.eval import reference_ops as ops

report={'status':'running','gpu':torch.cuda.get_device_name(),'hardwareQualified':False,'cases':[],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':'Finite synthetic shapes and synchronized CUDA Graph event timings; not full decoder/quality acceptance.'}
try:
    for width,outputs in ((768,4096),(1024,32768),(2048,11008),(4096,4096)):
        gen=torch.Generator().manual_seed(width)
        w=(torch.randn(outputs,width,generator=gen)*.02).half().cuda()
        x=torch.randn(8,width,generator=gen).cuda()
        for rows in (1,8):
            expected=StrictCudaKernels('cuda').linear(x[:rows],w)
            oracle=ops.linear(x[:1].cpu(),w[:3].cpu())
            assert torch.equal(expected[:1,:3].cpu().contiguous().view(torch.int32),oracle.view(torch.int32))
            for per in (8,16,32):
                warps=-(-width//(32*per));padded=1<<(warps-1).bit_length();groups=max(1,8//warps)
                plan=LinearPlan(width,1<<(width-1).bit_length(),per,warps,padded,groups)
                tile=1 if rows==1 else 8
                kernels=StrictCudaKernels('cuda');function=kernels._linear_function(plan,False,tile)
                out=torch.empty_like(expected);flag=kernels.new_error_flag()
                def launch():
                    kernels._launch(function,grid=(-(-outputs//groups),-(-rows//tile)),block=(32*warps,groups),
                                    pointers=(x,w,w,out,flag),integers=(rows,outputs))
                launch();kernels.raise_if_error(flag)
                assert torch.equal(out.view(torch.int32),expected.view(torch.int32))
                graph=torch.cuda.CUDAGraph()
                with torch.cuda.graph(graph):
                    for _ in range(40):launch()
                ms=[]
                for _ in range(3):
                    start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                    start.record();graph.replay();end.record();end.synchronize();ms.append(start.elapsed_time(end)/40)
                case={'width':width,'outputs':outputs,'rows':rows,'per':per,'rowTile':tile,'bitsEqual':True,
                      'eventMs':ms,'medianEventMs':statistics.median(ms),'identity':kernels.identity()}
                report['cases'].append(case)
                print(json.dumps({k:case[k] for k in ('width','rows','per','medianEventMs')}),flush=True)
                del graph
    report['status']='ok'
except Exception as exc:
    report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}))
raise SystemExit(report['status']!='ok')
