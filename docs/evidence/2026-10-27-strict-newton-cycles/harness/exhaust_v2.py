"""Exhaust all admitted FP32 bit patterns on SM120, comparing original nodes and instrumenting removed checks."""
import argparse,hashlib,json,os,struct,time
from pathlib import Path
import torch
from heteroes.eval import strict_cuda as sc
from normal_exp import transform

p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True)
a=p.parse_args();assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
torch.empty(1,device='cuda');k=sc.StrictCudaKernels('cuda')
header=''.join(f'#define {n} 0x{v:08x}u\n' for n,v in sc.reference_constants().items())
source=transform(sc._OPS_SOURCE)
assert source.count('return r;')>=2
start=source.index('__device__ __forceinline__ float normal_add');stop=source.index('typedef unsigned short',start)
raw=source[start:stop]
raw=raw.replace('return r;',r'''unsigned proof_bits=__float_as_uint(r),e=proof_bits&0x7f800000u;
  if(e==0 && (proof_bits&0x7fffffffu)!=0)atomicAdd(proof_stats+3,1ull);
  if(e==0x7f800000u)atomicAdd(proof_stats+4,1ull);
  return r;''')
source='__device__ unsigned long long* proof_stats;\n'+source[:start]+raw+source[stop:]
entry=r'''
extern "C" __global__ void setup(unsigned long long* stats){proof_stats=stats;}
extern "C" __global__ void check_domain(unsigned long long* stats,int first,int count) {
  for(int i=blockIdx.x*blockDim.x+threadIdx.x;i<count;i+=gridDim.x*blockDim.x) {
    unsigned bits=(unsigned)(first+i);float x=__uint_as_float(bits);unsigned a=0,b=0,c=0,d=0;
    float ar=original_reciprocal_(x,a),br=reciprocal_(x,b),cr=original_rsqrt_(x,c),dr=rsqrt_(x,d);
    if(__float_as_uint(ar)!=__float_as_uint(br) || __float_as_uint(cr)!=__float_as_uint(dr)) {
      atomicAdd(stats,1ull);atomicMin(stats+1,(unsigned long long)bits);
    }
    if(a!=b || c!=d || a || c)atomicAdd(stats+2,1ull);
  }
}
extern "C" __global__ void check_exp(unsigned long long* stats,int first,int count) {
  for(int i=blockIdx.x*blockDim.x+threadIdx.x;i<count;i+=gridDim.x*blockDim.x) {
    for(unsigned sign=0;sign<2;++sign) {
      unsigned bits=(unsigned)(first+i)|(sign<<31);float x=__uint_as_float(bits);unsigned a=0,b=0;
      float ar=original_exp_(x,a),br=exp_(x,b);
      if(__float_as_uint(ar)!=__float_as_uint(br)) {atomicAdd(stats,1ull);atomicMin(stats+1,(unsigned long long)bits);}
      if(a!=b || a)atomicAdd(stats+2,1ull);
    }
  }
}
'''
fns=k._compile('normal-exhaust-v2',header+source+entry,['setup','check_domain','check_exp'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)
u32=lambda x:struct.unpack('<I',struct.pack('<f',x))[0]
report={'gpu':torch.cuda.get_device_name(),'status':'running','sourceHashes':{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ('normal.py','normal_exp.py','exhaust_v2.py')},'cases':[],'builds':k._builds}
for name,lo,hi,mult in (('check_domain',u32(1e-30),u32(1e30),1),('check_exp',0,u32(80.),2)):
    stats=torch.tensor([0,2**63-1,0,0,0],dtype=torch.int64,device='cuda')
    k._launch(fns['setup'],grid=(1,1),block=(1,1),pointers=(stats,),integers=())
    started=time.perf_counter();step=2**23
    for offset in range(lo,hi+1,step):
        count=min(step,hi+1-offset)
        k._launch(fns[name],grid=(512,1),block=(256,1),pointers=(stats,),integers=(offset,count))
        if (offset-lo)//step%16==0:
            torch.cuda.synchronize();print(name,'checked',mult*(offset+count-lo),'elapsed',round(time.perf_counter()-started,2),flush=True)
    torch.cuda.synchronize();values=stats.cpu().tolist()
    item={'kernel':name,'inputPatterns':mult*(hi-lo+1),'firstBits':lo,'lastBits':hi,'mismatches':values[0],
          'firstMismatchBits':None if values[1]==2**63-1 else values[1],'failureFlagDifferences':values[2],
          'removedSubnormalChecksHit':values[3],'removedNonfiniteChecksHit':values[4],'seconds':time.perf_counter()-started}
    print(item,flush=True);report['cases'].append(item)
    assert values[0]==values[2]==values[3]==values[4]==0
report['status']='ok'
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
