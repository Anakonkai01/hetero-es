"""Finite exact-integer execution geometry sweep; all timings include metadata refresh."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('Need GPU opt-in and fresh receipt')
import torch
from heteroes.eval import integer_reference as reference
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval.strict_cuda import StrictCudaKernels,_check

def measure(run):
    run();torch.cuda.synchronize()
    g=torch.cuda.CUDAGraph()
    with torch.cuda.graph(g):
        for _ in range(20):run()
    for _ in range(3):g.replay()
    torch.cuda.synchronize();samples=[]
    for _ in range(3):
        start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
        start.record();g.replay();end.record();end.synchronize();samples.append(start.elapsed_time(end)/20)
    return samples

report={'status':'running','gpu':torch.cuda.get_device_name(),'hardwareQualified':False,'cases':[],
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'limits':'Synthetic matrices; CUDA Graph events exclude host overhead but include input/weight metadata each call. '
                 'CPU reference checks sampled outputs; execution variants compare all bits. Not model quality/throughput.'}
try:
    for width,outputs in ((768,4096),(1024,65536),(2048,11008),(4096,4096)):
        gen=torch.Generator().manual_seed(width)
        weight=(torch.randn(outputs,width,generator=gen)*.02).half().cuda()
        x=torch.randn(32,width,generator=gen).cuda()
        strict=StrictCudaKernels('cuda')
        for rows in (1,8,32):
            v=x[:rows];flag=strict.new_error_flag()
            baseline=measure(lambda:strict.linear(v,weight,error_flag=flag))
            for bits in (14,22):
                kernels=IntegerCudaKernels('cuda',magnitude_bits=bits)
                expected=kernels.linear(v,weight)
                oracle=reference.linear(v[:2].cpu(),weight[:3].cpu(),magnitude_bits=bits)
                assert torch.equal(expected[:2,:3].cpu().contiguous().view(torch.int32),oracle.view(torch.int32))
                options=[('simt',1,16,4),('mma',1,16,4),('mma',1,32,4)]
                if rows!=1:options += [('mma',s,32,4) for s in (2,4,8) if s*rows*outputs*8<=kernels.max_partial_bytes]
                for mode,split,tile,warps in options:
                    def run():return kernels.linear(v,weight,error_flag=flag,implementation=mode,split_k=split,row_tile=tile,warps=warps)
                    actual=run();kernels.raise_if_error(flag)
                    assert torch.equal(actual.view(torch.int32),expected.view(torch.int32))
                    ms=measure(run);kernels.raise_if_error(flag)
                    case={'width':width,'outputs':outputs,'rows':rows,'magnitudeBits':bits,'mode':mode,'splitK':split,
                          'rowTile':tile,'warps':warps,'eventMs':ms,'medianEventMs':statistics.median(ms),
                          'strictMs':statistics.median(baseline),'bitsEqual':True,'identity':kernels.identity()}
                    report['cases'].append(case)
                    print(json.dumps({k:case[k]for k in ('width','rows','magnitudeBits','mode','splitK','rowTile','medianEventMs','strictMs')}),flush=True)
    report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}))
raise SystemExit(report['status']!='ok')
