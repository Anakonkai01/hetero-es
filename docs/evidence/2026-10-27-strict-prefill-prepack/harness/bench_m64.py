"""Projection-only paired control; packing cost included, one bounded scratch per call."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from prepack_m64 import PackedPrefill

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
k=IntegerCudaKernels('cuda',magnitude_bits=22)
g=torch.Generator(device='cuda').manual_seed(923)
report={'gpu':torch.cuda.get_device_name(),'identity':k.identity(),'prototypeSha256':hashlib.sha256(Path(__file__).with_name('prepack_m64.py').read_bytes()).hexdigest(),'cases':[],'limits':'Finite B22 operator microbenchmarks, not end-to-end gain or cross-platform acceptance.'}
def timing(call):
    call();torch.cuda.synchronize()
    graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        for _ in range(8):call()
    times=[]
    for _ in range(9):
        start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
        start.record();graph.replay();end.record();end.synchronize()
        times.append(start.elapsed_time(end)*1000/8)
    return times
for rows in (888,1024):
 for width,outputs in ((896,9728),(4864,896),(896,1152),(896,896)):
    x=torch.randn(rows,width,device='cuda',generator=g)
    w=(torch.randn(outputs,width,device='cuda',generator=g)*.03).half()
    k._begin_request([w]);flag=k.new_error_flag()
    prepared=k.quantize_input(x,_packed=True,error_flag=flag);ew=k._weight_exponents(w,flag)
    def base():return k._linear(x,w,row_tile=32,prepared=prepared,error_flag=flag)
    expected=base()
    item={'width':width,'outputs':outputs,'rows':rows,'variants':[]}
    variants=[('stream',base)]
    for columns in (32,64):
        proto=PackedPrefill(k,width,columns)
        def run(proto=proto):
            packed=proto.pack(w,ew)
            out=torch.empty_like(expected)
            return proto.project(prepared,packed,ew,out,flag)
        assert torch.equal(run().view(torch.int32),expected.view(torch.int32))
        variants.append((f'packed-n{columns}',run))
    for label,call in variants:
        times=timing(call)
        item['variants'].append({'label':label,'microseconds':times,'median':statistics.median(times)})
        print(rows,width,outputs,label,round(statistics.median(times),2),'us',flush=True)
    assert flag.item()==0
    report['cases'].append(item);k._end_request()
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
