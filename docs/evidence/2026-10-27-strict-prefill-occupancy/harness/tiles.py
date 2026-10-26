"""Compare M32/N64 with M64 prefill tiles, retaining the same exact integer projection and flags."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--src',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
sys.path.insert(0,a.src)
import torch
from heteroes.eval import integer_cuda as ic
k=ic.IntegerCudaKernels('cuda',magnitude_bits=22)
gen=torch.Generator(device='cuda').manual_seed(731)
report={'gpu':torch.cuda.get_device_name(),'arch':k.arch,'source':a.src,'cases':[]}
rows=888

def timing(call):
    call();torch.cuda.synchronize()
    graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        for _ in range(8):call()
    times=[]
    for _ in range(9):
        begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
        begin.record();graph.replay();end.record();end.synchronize()
        times.append(begin.elapsed_time(end)*1000/8)
    return times

for width,outputs in ((896,9728),(4864,896),(896,1152),(896,896)):
    x=torch.randn(rows,width,device='cuda',generator=gen)
    w=(torch.randn(outputs,width,device='cuda',generator=gen)*.03).half()
    k._begin_request([w])
    flag=k.new_error_flag();prepared=k.quantize_input(x,_packed=True,error_flag=flag);planes,ex=prepared
    ew=k._weight_exponents(w,flag)
    bias=torch.empty(0,dtype=torch.float16,device='cuda')
    expected=k._linear(x,w,None,row_tile=32,split_k=1,implementation='mma',prepared=prepared,stream_columns=64,error_flag=flag)
    item={'width':width,'outputs':outputs,'rows':rows,'variants':[]}
    for mt,nt,stages,resident in ((32,64,2,3),(32,32,2,4),(16,64,2,4),(16,32,2,6)):
        defines={'WIDTH':width,'MAGNITUDE_BITS':22,'DIGITS':3,'HAS_BIAS':0,'M_GROUPS':mt//16,'WARPS':4,'SPLIT_K':1,'PACKED_INPUT':1,'WEIGHT_READ32':0,'WEIGHT_PREFETCH':1,'FAST_CONVERT':1,'STREAM_LDSM_INPUT':1,'JN':nt//32,'STAGES':stages,'STREAM_MIN_BLOCKS':resident}
        source=''.join(f'#define {name} {value}\n' for name,value in defines.items())+ic._SOURCE
        name=f'prefill-occupancy-m{mt}-n{nt}-s{stages}-r{resident}-k{width}'
        fn=k._compile(name,source,['integer_stream'],integer_mma=True)['integer_stream']
        result=torch.empty((rows,outputs),dtype=torch.float32,device='cuda')
        def call():
            k._launch(fn,grid=(-(-outputs//nt),-(-rows//mt),1),block=(128,1),pointers=(planes,w,bias,ex,ew,result,flag,result),integers=(rows,outputs))
        call();torch.cuda.synchronize()
        assert not int(flag.item()) and torch.equal(result.view(torch.int32),expected.view(torch.int32)),name
        times=timing(call)
        attr=k._driver.CUfunction_attribute
        data={'m':mt,'n':nt,'stages':stages,'minBlocks':resident,'microseconds':times,'median':statistics.median(times),'registers':ic.sc._check(k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_NUM_REGS,fn)),'localBytes':ic.sc._check(k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_LOCAL_SIZE_BYTES,fn)),'sharedBytes':ic.sc._check(k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES,fn)),'residentCtas':ic.sc._check(k._driver.cuOccupancyMaxActiveBlocksPerMultiprocessor(fn,128,0)),'build':k._builds[name]}
        item['variants'].append(data)
        print(width,outputs,'m',mt,'n',nt,'us',round(data['median'],1),'regs',data['registers'],'local',data['localBytes'],'resident',data['residentCtas'],flush=True)
    report['cases'].append(item)
    k._end_request()
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
