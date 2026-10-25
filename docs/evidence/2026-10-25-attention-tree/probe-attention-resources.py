"""Record actual compiled attention resources; do not infer local spills from source alone."""
import argparse,json,os,hashlib
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1'or a.out.exists():p.error('GPU opt-in and fresh output required')
import torch
from heteroes.eval.strict_cuda import StrictCudaKernels,_check
r={'hardwareQualified':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'gpu':torch.cuda.get_device_name(),'status':'running'}
try:
 context=torch.empty(1,device='cuda');k=StrictCudaKernels('cuda');fn=k._ops('strict_attention');attrs=k._driver.CUfunction_attribute
 r['resources']={name:int(_check(k._driver.cuFuncGetAttribute(getattr(attrs,'CU_FUNC_ATTRIBUTE_'+name),fn)))for name in('NUM_REGS','LOCAL_SIZE_BYTES','SHARED_SIZE_BYTES','MAX_THREADS_PER_BLOCK')};r['kernelIdentity']=k.identity();r['status']='ok'
except Exception as e:r.update(status='error',errorType=type(e).__name__,error=str(e))
with a.out.open('x')as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps({key:r.get(key)for key in('status','resources','error')}));raise SystemExit(r['status']!='ok')
