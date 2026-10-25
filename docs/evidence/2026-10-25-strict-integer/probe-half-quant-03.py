"""Exhaust every admitted finite half value and row exponent against exact binary64 power-of-two rounding."""
import argparse,json,hashlib,os
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh output required')
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels,_SOURCE
from heteroes.eval import strict_cuda as sc
_context = torch.empty(1,device="cuda")
stub=r'''
extern "C" __global__ void probe_quant(int* out) {
 int i=blockIdx.x*256+threadIdx.x;
 if(i>=40*65536)return;
 int exponent=i/65536-24;u16 u=(u16)i;unsigned a=u&0x7fffu, e=a>>10;
 int actual=!a ? -1000 : e ? (int)e-15 : 31-__clz(a)-24;
 out[i]=(a>=0x7c00u || actual>exponent) ? (-2147483647-1) : quant_half(u,exponent);
}
'''
report={'status':'running','gpu':torch.cuda.get_device_name(),'hardwareQualified':False,'cases':[],
 'probeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'limit':'All admitted FP16 bit patterns and row exponent pairs for weight quantization only; not graph qualification.'}
try:
 bits=torch.arange(65536,dtype=torch.int32);half=bits.to(torch.int16).view(torch.float16);values=half.double()
 floors=torch.tensor([(-1000 if not (u&0x7fff) else ((u&0x7fff)>>10)-15 if ((u&0x7fff)>>10) else (u&1023).bit_length()-1-24)for u in range(65536)])
 finite=(bits&0x7fff)<0x7c00
 for b in (14,22):
  k=IntegerCudaKernels('cuda',magnitude_bits=b)
  header=f'#define WIDTH 32\n#define MAGNITUDE_BITS {b}\n#define DIGITS {2 if b==14 else 3}\n#define HAS_BIAS 0\n#define M_GROUPS 1\n#define WARPS 4\n#define SPLIT_K 1\n'
  fn=k._compile('probe-half-'+str(b),header+_SOURCE+stub,['probe_quant'],integer_mma=True)['probe_quant']
  out=torch.empty((40,65536),dtype=torch.int32,device='cuda');k._launch(fn,grid=(out.numel()+255)//256,block=(256,1),pointers=(out,),integers=())
  actual=out.cpu();count=0
  for row,e in enumerate(range(-24,16)):
   valid=finite&(floors<=e);count+=int(valid.sum())
   expected=torch.full((65536,),-(2**31),dtype=torch.int32)
   expected[valid]=torch.round(values[valid]*2.0**(b-1-e)).to(torch.int32)
   assert bool((expected[valid].abs()<=2**b).all())
   assert torch.equal(actual[row],expected),(b,e,int((actual[row]!=expected).sum()))
  report['cases'].append({'magnitudeBits':b,'admittedPairs':count,'allBitPatternsChecked':65536,'rowExponents':[-24,15],'allEqual':True,'identity':k.identity()})
 report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
