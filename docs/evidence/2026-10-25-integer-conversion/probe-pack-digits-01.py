"""Exhaust every signed q in the admitted radix-packing domain using an independent CPU integer oracle."""
import argparse,hashlib,json,os
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('Need GPU opt-in and fresh output')
import numpy as np
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels,_SOURCE
context=torch.empty(1,device='cuda')
stub=r'''
extern "C" __global__ void probe_pack(int* out,int count,int first) {
 int i=blockIdx.x*256+threadIdx.x;if(i>=count)return;
 unsigned words[DIGITS]={};pack_digits(words,first+i,0);
 for(int d=0;d<DIGITS;++d)out[(size_t)d*count+i]=(int)words[d];
}
'''
report={'status':'running','hardwareQualified':False,'gpu':torch.cuda.get_device_name(),'probeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'limits':'Every admitted signed q; byte position zero. Exact CPU signed-digit oracle, not graph/quality/throughput acceptance.','cases':[]}
try:
 for b in (14,22):
  k=IntegerCudaKernels('cuda',magnitude_bits=b);digits=2 if b==14 else 3
  header=f'#define WIDTH 32\n#define MAGNITUDE_BITS {b}\n#define DIGITS {digits}\n#define HAS_BIAS 0\n#define M_GROUPS 1\n#define WARPS 4\n#define SPLIT_K 1\n'
  fn=k._compile('exhaust-pack-'+str(b),header+_SOURCE+stub,['probe_pack'],integer_mma=True)['probe_pack']
  count=2**(b+1)+1;first=-(2**b);out=torch.empty((digits,count),dtype=torch.int32,device='cuda')
  k._launch(fn,grid=(count+255)//256,block=(256,1),pointers=(out,),integers=(count,first))
  actual=out.cpu().numpy();remaining=np.arange(first,first+count,dtype=np.int32)
  for d in range(digits):
   digit=((remaining+128)&255)-128
   assert np.array_equal(actual[d],digit&255),(b,d)
   remaining=(remaining-digit)//256
  assert not np.any(remaining)
  report['cases'].append({'magnitudeBits':b,'admittedValues':count,'allEqual':True,'identity':k.identity()})
 report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
