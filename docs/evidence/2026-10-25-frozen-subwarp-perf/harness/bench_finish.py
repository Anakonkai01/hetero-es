"""Captured operator sweep over actual rank-8 decoder shapes; variants share exact input bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--gpu',action='store_true')
parser.add_argument('--ranks',type=int,nargs='+',default=[8,32])
parser.add_argument('--rows',type=int,nargs='+',default=[1,8,32])
parser.add_argument('--outputs',type=int,nargs='+',default=[256,896,960,2048,2560,4864,5632])
args=parser.parse_args()
if args.out.exists():parser.error('Existing evidence')
if not args.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':parser.error('GPU opt-in')
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
k=StrictCudaKernels('cuda')
generator=torch.Generator().manual_seed(433)
report={'gpu':torch.cuda.get_device_name(0),'torch':torch.__version__,'cuda':torch.version.cuda,'cases':[]}
for rows in args.rows:
 for rank in args.ranks:
  for outputs in args.outputs:
   mid=torch.randn(rows,rank,generator=generator).cuda()
   weight=(torch.randn(outputs,rank,generator=generator)*.02).half().cuda()
   base=torch.randn(rows,outputs,generator=generator).cuda()
   expected=k.lora_finish(mid,weight,base,2.,execution='warp')
   case={'rows':rows,'rank':rank,'outputs':outputs,'variants':[]}
   for execution,tile in (('warp',8),('output',1),('output',2),('output',4),('output',8)):
    flag=k.new_error_flag()
    k.lora_finish(mid,weight,base,2.,execution=execution,row_tile=tile,error_flag=flag)
    graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
     actual=k.lora_finish(mid,weight,base,2.,execution=execution,row_tile=tile,error_flag=flag)
    graph.replay();torch.cuda.synchronize();k.raise_if_error(flag)
    assert torch.equal(actual.view(torch.int32),expected.view(torch.int32)),(rows,rank,outputs,execution,tile)
    raw=[]
    for _ in range(5):
     begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
     begin.record()
     for _ in range(100):graph.replay()
     end.record();end.synchronize()
     raw.append(begin.elapsed_time(end)/100)
    case['variants'].append({'execution':execution,'rowTile':tile,'eventMs':raw,'medianEventMs':statistics.median(raw)})
    del graph
   report['cases'].append(case)
   print(rows,rank,outputs,[(v['execution'],v['rowTile'],round(v['medianEventMs']*1000,2)) for v in case['variants']],flush=True)
report['kernelIdentity']=k.identity()
with args.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
