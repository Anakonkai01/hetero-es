"""Short full-weight B22 single-row scheduling sweep, including vocabulary-sized heads."""
import argparse,json,os,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists():p.error('Existing evidence')
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':p.error('GPU opt-in')
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference as oracle
k=IntegerCudaKernels('cuda',magnitude_bits=22)
gen=torch.Generator().manual_seed(701)
report={'gpu':torch.cuda.get_device_name(0),'cases':[]}
for width,outputs in [(896,128),(896,896),(896,4864),(4864,896),(960,960),(2560,960),
                      (2048,256),(2048,2048),(5632,2048),(960,49152),(896,151936),(2048,32000)]:
    cx=torch.randn(1,width,generator=gen);cw=(torch.randn(outputs,width,generator=gen)*.02).half()
    x,w=cx.cuda(),cw.cuda();k._begin_request((w,))
    reference=k.linear(x,w,implementation='simt')
    expected=oracle.linear(cx,cw[:3],magnitude_bits=22)
    assert torch.equal(reference[:,:3].cpu().contiguous().view(torch.int32),expected.view(torch.int32))
    case={'width':width,'outputs':outputs,'variants':[]}
    for mode,split in [('simt',1),('simt',2),('simt',4),('simt',8),('mma',1),('mma',4)]:
        flag=k.new_error_flag();k.linear(x,w,error_flag=flag,implementation=mode,split_k=split)
        graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):result=k.linear(x,w,error_flag=flag,implementation=mode,split_k=split)
        graph.replay();torch.cuda.synchronize();k.raise_if_error(flag)
        assert torch.equal(result.view(torch.int32),reference.view(torch.int32)),(width,outputs,mode,split)
        raw=[]
        for _ in range(5):
            begin,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
            begin.record()
            for _ in range(30):graph.replay()
            end.record();end.synchronize();raw.append(begin.elapsed_time(end)/30)
        case['variants'].append({'mode':mode,'split':split,'eventMs':raw,'medianEventMs':statistics.median(raw)})
        del graph
    report['cases'].append(case)
    print(width,outputs,[(v['mode'],v['split'],round(v['medianEventMs']*1000,2)) for v in case['variants']],flush=True)
    k._end_request();del x,w,reference
report['identity']=k.identity()
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
