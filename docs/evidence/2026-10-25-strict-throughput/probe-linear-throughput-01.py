"""Finite synthetic projection sweep: no model, four widths, identical arithmetic across row tiles."""
import argparse
import json
import os
from pathlib import Path
import statistics
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--gpu',action='store_true')
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists() or not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':
 p.error('Need a fresh receipt and explicit GPU acceptance')
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from heteroes.eval import reference_ops as ops
kernels=StrictCudaKernels('cuda')
report={'status':'running','hardwareQualified':False,'gpu':torch.cuda.get_device_name(),
        'limits':'Synthetic finite matrices. Event intervals include host-launch gaps; host wall is synchronized. '
                 'No full-model, quality or universal performance claim.', 'cases':[]}
try:
 for width,outputs in ((768,4096),(1024,65536),(2048,11008),(4096,4096)):
  gen=torch.Generator().manual_seed(width)
  weight=(torch.randn(outputs,width,generator=gen)*0.02).half().cuda()
  x=torch.randn(32,width,generator=gen).cuda()
  for rows in (1,8,32):
   expected=None
   for tile in (1,2,4,8):
    flag=kernels.new_error_flag()
    result=kernels.linear(x[:rows],weight,row_tile=tile,error_flag=flag)
    kernels.raise_if_error(flag)
    if expected is None:
     expected=result.clone()
     oracle=ops.linear(x[:1].cpu(),weight[:3].cpu())
     assert torch.equal(result[:1,:3].cpu().contiguous().view(torch.int32),oracle.view(torch.int32))
    assert torch.equal(expected.view(torch.int32),result.view(torch.int32))
    events,host=[],[]
    for _ in range(3):
     torch.cuda.synchronize()
     start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
     t=time.perf_counter();start.record()
     for _ in range(3):
      result=kernels.linear(x[:rows],weight,row_tile=tile,error_flag=flag)
     end.record();end.synchronize()
     host.append((time.perf_counter()-t)*1000/3)
     events.append(start.elapsed_time(end)/3)
    kernels.raise_if_error(flag)
    report['cases'].append({'width':width,'outputs':outputs,'rows':rows,'rowTile':tile,
                            'medianEventMsPerCall':statistics.median(events),
                            'medianHostMsPerCall':statistics.median(host),'bitsEqual':True})
 report['kernelIdentity']=kernels.identity();report['status']='ok'
except Exception as error:
 report.update(status='error',errorType=type(error).__name__,error=str(error))
with a.out.open('x') as stream:
 json.dump(report,stream,indent=2);stream.write('\n')
print(json.dumps({'status':report['status'],'cases':len(report['cases'])}))
raise SystemExit(0 if report['status']=='ok' else 1)
