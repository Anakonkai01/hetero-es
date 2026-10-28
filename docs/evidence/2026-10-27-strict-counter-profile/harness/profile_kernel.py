"""One marked frozen B22 kernel per process; profiler counters are not end-to-end benchmark timings."""
import argparse,hashlib,json,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--case',choices=['prefill-gate','prefill-down','decode-gate','decode-down','bound-head','attention'],required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
import torch
from heteroes.eval import integer_cuda as ic
from heteroes.eval import strict_cuda as sc
from heteroes.eval.integer_lm_head import BoundedLmHead
k=ic.IntegerCudaKernels('cuda',magnitude_bits=22);g=torch.Generator(device='cuda').manual_seed(817);flag=k.new_error_flag()
weights=[]
if a.case=='attention':
    repeats,dim,rows,slot=7,64,32,512
    lens=[17+(i%8)*4+16 for i in range(rows)]
    q=torch.randn(14,rows,dim,device='cuda',generator=g);key=torch.randn(2,rows*slot,dim,device='cuda',generator=g);value=torch.randn_like(key)
    ranges=torch.tensor([(i*slot,l,l-1) for i,l in enumerate(lens)],dtype=torch.int32,device='cuda')
    layout=sc._PackedAttentionLayout(ranges,rows,rows*slot,max(lens))
    def run():return k.attention_packed(q,key,value,layout,repeats,1./8,error_flag=flag)
    shape={'queries':rows,'lengths':lens,'heads':14,'kvHeads':2,'dim':dim,'slot':slot}
else:
    rows,width,outputs={'prefill-gate':(888,896,4864),'prefill-down':(888,4864,896),'decode-gate':(32,896,9728),'decode-down':(32,4864,896),'bound-head':(32,896,151936)}[a.case]
    x=torch.randn(rows,width,device='cuda',generator=g)
    if a.case=='decode-gate':weights=[(torch.randn(outputs//2,width,device='cuda',generator=g)*.03).half() for _ in range(2)]
    else:weights=[(torch.randn(outputs,width,device='cuda',generator=g)*.03).half()]
    k._begin_request(weights);prepared=k.quantize_input(x,_packed=True,error_flag=flag)
    shape={'rows':rows,'width':width,'outputs':outputs}
    if a.case=='bound-head':
        head=BoundedLmHead(k);head.prepare(weights[0],flag)
        def run():return head.bounds(prepared,weights[0])
    elif a.case=='decode-gate':
        def run():return k.linear_many(None,weights,error_flag=flag,prepared=prepared,decode_target_ctas_per_sm=8)
    elif a.case=='decode-down':
        def run():return k.linear_decode(None,weights[0],error_flag=flag,prepared=prepared,target_ctas_per_sm=8)
    else:
        def run():return k._linear(x,weights[0],error_flag=flag,prepared=prepared)
for _ in range(3):run()
torch.cuda.synchronize();assert int(flag.item())==0
torch.cuda.profiler.start();run();torch.cuda.synchronize();torch.cuda.profiler.stop()
assert int(flag.item())==0
report={'status':'ok','case':a.case,'shape':shape,'identity':k.identity(),'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'builds':k._builds,'limits':'One synthetic matching-shape kernel, hardware counters only; no trained-model/whole-generation or learning acceptance.'}
if a.case=='bound-head':head.clear()
if weights:k._end_request()
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':'ok','case':a.case,'shape':shape}),flush=True)
