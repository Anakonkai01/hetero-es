"""Warm-table CUDA-graph operator screening; no end-to-end or cold-cache speed claim."""
import argparse,hashlib,json,os,statistics
from pathlib import Path
import torch
from gpu_lookup import LookupKernels
from heteroes.eval import strict_cuda as sc
from lookup import build_table

FULL=r'''
__device__ __forceinline__ float reciprocal_full(float x,const unsigned* table,unsigned& bad) {
  if (!(x>=k(DOMAIN_LOW) && x<=k(DOMAIN_HIGH))) return reciprocal_(x,bad);
  unsigned u=__float_as_uint(x);
  int exponent=(int)(u>>23)-127;
  return __uint_as_float(table[u&0x7fffff]-(unsigned)(exponent*0x800000));
}
extern "C" __global__ void full_silu_mul(const float* gate,const float* up,const unsigned* table,float* out,int* error,int count) {
  unsigned bad=0;int i=blockIdx.x*256+threadIdx.x;
  if(i<count) {
    float x=load(gate+i,bad),small=exp_(-fabsf(x),bad);
    float denominator=reciprocal_full(add_(1.0f,small,bad),table,bad);
    float positive=mul_(x,denominator,bad),negative=mul_(mul_(x,small,bad),denominator,bad);
    out[i]=mul_(x>=0 ? positive : negative,load(up+i,bad),bad);
  }
  report(error,bad);
}
'''
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
k=LookupKernels();table=torch.from_numpy(build_table()).cuda()
header=''.join(f'#define {key} 0x{v:08x}u\n' for key,v in sc.reference_constants().items())
fn=k.owner._compile('exact-reciprocal-full-v1',header+sc._OPS_SOURCE+FULL,['full_silu_mul'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['full_silu_mul']
report={'status':'running','gpu':torch.cuda.get_device_name(),'tableSha256':k.table_sha256,'compressedBytes':k.table_bytes,'fullBytes':table.numel()*table.element_size(),'prototypeSha256':hashlib.sha256(Path(__file__).with_name('gpu_lookup.py').read_bytes()).hexdigest(),'cases':[],'limits':__doc__}
def timing(call):
    call();torch.cuda.synchronize();graph=torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        for _ in range(8):call()
    times=[]
    for _ in range(11):
        start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
        start.record();graph.replay();end.record();end.synchronize();times.append(start.elapsed_time(end)*1000/8)
    return times
gen=torch.Generator(device='cuda').manual_seed(53)
for rows,width in ((32,4864),(888,4864),(32,2048)):
    x=torch.randn(rows,width,device='cuda',generator=gen)*5;y=torch.randn_like(x);flag=k.owner.new_error_flag()
    def base():return k.owner.silu_mul(x,y,error_flag=flag)
    def packed():return k.silu_mul(x,y,error_flag=flag)
    def full():
        out=torch.empty_like(x)
        k.owner._launch(fn,grid=-(-x.numel()//256),block=(256,1),pointers=(x,y,table,out,flag),integers=(x.numel(),))
        return out
    expected=base()
    item={'rows':rows,'width':width,'variants':[]}
    for name,call in [('newton',base),('nibble-table',packed),('full-table',full)]:
        assert torch.equal(call().view(torch.int32),expected.view(torch.int32)) and int(flag.item())==0
        times=timing(call);item['variants'].append({'name':name,'microseconds':times,'median':statistics.median(times)})
        print(rows,width,name,round(statistics.median(times),3),'us',flush=True)
    report['cases'].append(item)
report['builds']=k.owner._builds;report['status']='ok'
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
