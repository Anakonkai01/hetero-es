"""Every carry boundary retains the independent adjacent-pair tree, signed zeros, FTZ and failures."""
import os
import pytest
import torch
from heteroes.eval import strict_cuda as sc, reference_ops as ops
from heteroes.eval.reference_ops import ReferenceArithmeticError
pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1'or not torch.cuda.is_available(),reason='GPU opt-in')
STUB=r'''
extern "C" __global__ void probe_tree(const float* values,const int* counts,float* out,int* error,int rows,int width) {
 int row=blockIdx.x*blockDim.x+threadIdx.x;
 if(row>=rows)return;
 unsigned bad=0;Tree t;t.n=0;
 for(int j=0;j<counts[row];++j)push(t,load(values+(size_t)row*width+j,bad),bad);
 out[row]=finish(t,bad);report(error,bad);
}
'''
def run(values,counts):
 k=sc.StrictCudaKernels('cuda');header=''.join(f'#define {key} 0x{value:08x}u\n'for key,value in sc.reference_constants().items());fn=k._compile('test-tree',header+sc._OPS_SOURCE+STUB,['probe_tree'],ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)['probe_tree'];out=torch.empty(values.shape[0],device='cuda');flag=k.new_error_flag()
 k._launch(fn,grid=(values.shape[0]+63)//64,block=(64,1),pointers=(values,counts,out,flag),integers=values.shape)
 k.raise_if_error(flag);return out

def test_tree_prefixes_carry_boundaries_and_signed_zero_without_adding_identity_nodes():
 counts=sorted(set(list(range(1,66))+[2**b+d for b in range(7,13)for d in(-1,0,1)if 2**b+d<=4096]));counts=[c for c in counts for _ in range(3)];width=max(counts);gen=torch.Generator().manual_seed(129)
 values=torch.randn(len(counts),width,generator=gen)*16
 cancellation=torch.tensor([2.**24,1.,-2.**24,1.]).repeat((width+3)//4)[:width]
 tiny=torch.tensor([0x00800000,0x80800001,0x80000000,1,0x807fffff],dtype=torch.int64).to(torch.int32).view(torch.float32).repeat((width+4)//5)[:width]
 for row in range(len(counts)):
  if row%3==0:values[row]=cancellation
  elif row%3==1:values[row]=-0.
  else:values[row]=tiny
 expected=torch.stack([ops.pairwise_sum(values[row,:count])for row,count in enumerate(counts)])
 actual=run(values.cuda(),torch.tensor(counts,dtype=torch.int32,device='cuda')).cpu()
 assert torch.equal(actual.view(torch.int32),expected.view(torch.int32))

@pytest.mark.parametrize('values',[[torch.finfo(torch.float32).max,torch.finfo(torch.float32).max,-torch.finfo(torch.float32).max],[0.,float('nan'),0.],[float('inf'),float('-inf'),0.]])
def test_tree_still_reports_intermediate_overflow_and_nonfinite(values):
 with pytest.raises(ReferenceArithmeticError,match='Nonfinite'):run(torch.tensor([values],device='cuda'),torch.tensor([len(values)],dtype=torch.int32,device='cuda'))
