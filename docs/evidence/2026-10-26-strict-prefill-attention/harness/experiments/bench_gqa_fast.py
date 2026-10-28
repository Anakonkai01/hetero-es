import os,argparse,statistics
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels
from gqa_fast import install
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1'
ks=[StrictCudaKernels('cuda') for _ in range(2)]
for ker in ks:ker._attention_entry='strict_attention_gqa'
install(ks[1])
for keys in (32,64,128,270,512):
    torch.manual_seed(9)
    q=torch.randn(14,32,64,device='cuda');k=torch.randn(2,32*keys,64,device='cuda');v=torch.randn_like(k)
    spans=[(1,keys,keys-1)]*32;expected=None;times=[];regs=[]
    for ker in ks:
        layout=ker.attention_layout(spans);flag=ker.new_error_flag()
        def run():return ker.attention_packed(q,k,v,layout,7,.125,error_flag=flag)
        out=run();assert flag.item()==0
        if expected is None:expected=out
        else:assert torch.equal(out.view(torch.int32),expected.view(torch.int32))
        g=torch.cuda.CUDAGraph()
        with torch.cuda.graph(g):
            for _ in range(25):captured=run()
        samples=[]
        for _ in range(9):
            s,e=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            s.record()
            for _ in range(20):g.replay()
            e.record();torch.cuda.synchronize();samples.append(s.elapsed_time(e)*1000/500)
        times.append(statistics.median(samples))
        d=ker._driver;regs.append(d.cuFuncGetAttribute(d.CUfunction_attribute.CU_FUNC_ATTRIBUTE_NUM_REGS,ker._functions['ops']['strict_attention_gqa']))
    print(keys,times,times[0]/times[1],regs,flush=True)
