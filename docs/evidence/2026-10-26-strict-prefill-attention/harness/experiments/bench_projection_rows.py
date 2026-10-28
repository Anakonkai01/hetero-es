import argparse,os,statistics
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from projection_rows import install
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1'
for rows,width,outputs in [(888,896,1152),(2879,896,1152),(2879,896,896),(2879,896,4864),(2879,4864,896)]:
    torch.manual_seed(7)
    x=torch.randn(rows,width,device='cuda');w=(torch.randn(outputs,width,device='cuda')*.03).half()
    ks=[IntegerCudaKernels('cuda',magnitude_bits=22) for _ in range(2)];install(ks[1])
    expected=None;result=[]
    for ker in ks:
        ker._begin_request([w]);f=ker.new_error_flag()
        def run():return ker.linear(x,w,error_flag=f)
        out=run();torch.cuda.synchronize();assert f.item()==0
        if expected is None:expected=out
        else:assert torch.equal(out.view(torch.int32),expected.view(torch.int32))
        g=torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):captured=run()
        times=[]
        for _ in range(7):
            s,e=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            s.record()
            for _ in range(10):g.replay()
            e.record();torch.cuda.synchronize();times.append(s.elapsed_time(e)*1000/10)
        result.append(statistics.median(times));ker._end_request()
    print((rows,width,outputs),result,'ratio',result[0]/result[1],flush=True)
