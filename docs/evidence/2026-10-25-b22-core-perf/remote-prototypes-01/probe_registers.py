import json,os
from pathlib import Path
assert os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1'
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from pair_load import PairLoadKernels
context=torch.empty(1,device='cuda')
result=[]
for label,klass in [('scalar',IntegerCudaKernels),('pair',PairLoadKernels)]:
 k=klass('cuda',magnitude_bits=22)
 for width in (896,960,2048,5632):
  for split in (1,2,4,8):
   f=k._integer_functions(width,False,32,4,split,packed_input=True)['integer_linear']
   regs=k._driver.cuFuncGetAttribute(k._driver.CUfunction_attribute.CU_FUNC_ATTRIBUTE_NUM_REGS,f)
   occupancy=k._driver.cuOccupancyMaxActiveBlocksPerMultiprocessor(f,128,0)
   result.append({'kind':label,'width':width,'split':split,'regs':[int(v) for v in regs],
                  'activeBlocks':[int(v) for v in occupancy]})
print(json.dumps({'gpu':torch.cuda.get_device_name(0),'data':result},indent=2))
