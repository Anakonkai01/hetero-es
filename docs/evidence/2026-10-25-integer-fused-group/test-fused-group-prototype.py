"""A grouped launch must preserve each independent matrix's exact arithmetic, errors and live bindings."""
import os
import pytest
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval.integer_reference import linear as oracle
from heteroes.eval.reference_ops import ReferenceArithmeticError
pytestmark=pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or not torch.cuda.is_available(),reason='GPU opt-in')

@pytest.mark.parametrize('bits',[14,22])
@pytest.mark.parametrize('rows,width,outputs',[(1,33,(7,17)),(3,257,(17,11,37)),(19,769,(3,33,35)),(32,67,(65,9))])
def test_group_exact_independent_rows_tails_biases_and_splits(bits,rows,width,outputs):
 from integer_grouped_prototype import grouped
 g=torch.Generator().manual_seed(131+rows);x=torch.randn(rows,width,generator=g);x[0]=-0.;weights=[(torch.randn(n,width,generator=g)*.03).half()for n in outputs];biases=[None if i%2==0 else torch.randn(n,generator=g).half()for i,n in enumerate(outputs)]
 k=IntegerCudaKernels('cuda',magnitude_bits=bits);gx=x.cuda();ws=[w.cuda()for w in weights];bs=[None if b is None else b.cuda()for b in biases]
 expected=[oracle(x,w,b,magnitude_bits=bits)for w,b in zip(weights,biases)]
 for split in (1,2,8):
  actual=grouped(k,gx,ws,bs,split_k=split)
  for a,e in zip(actual,expected):assert torch.equal(a.cpu().view(torch.int32),e.view(torch.int32)),(bits,rows,width,split)


def test_live_metadata_capture_refresh_nonfinite_and_budget_guards():
 from integer_grouped_prototype import grouped
 k=IntegerCudaKernels('cuda',magnitude_bits=22);g=torch.Generator().manual_seed(63);x=torch.randn(8,263,generator=g).cuda();ws=[(torch.randn(n,263,generator=g)*.02).half().cuda()for n in (17,35,9)];saved=[w.clone()for w in ws];flag=k.new_error_flag();parents=[]
 for factor in (1.,-16.,1.):
  ws[1].copy_(saved[1]*factor);k._begin_request(ws)
  try:
   actual=grouped(k,x,ws,error_flag=flag,split_k=8)
   for a,w in zip(actual,ws):assert torch.equal(a.cpu().view(torch.int32),oracle(x.cpu(),w.cpu(),magnitude_bits=22).view(torch.int32))
   graph=torch.cuda.CUDAGraph()
   with torch.cuda.graph(graph):captured=grouped(k,x,ws,error_flag=flag,split_k=8)
   graph.replay();torch.cuda.synchronize();k.raise_if_error(flag)
   assert all(torch.equal(a.view(torch.int32),b.view(torch.int32))for a,b in zip(actual,captured));parents.append(actual[1].clone())
  finally:k._end_request()
 assert torch.equal(parents[0],parents[2])and not torch.equal(parents[0],parents[1])
 ws[2][-1,-1]=float('nan')
 with pytest.raises(ReferenceArithmeticError,match='Nonfinite'):grouped(k,x,ws)
 flag=k.new_error_flag();grouped(k,x,ws,error_flag=flag)
 with pytest.raises(ReferenceArithmeticError,match='Nonfinite'):k.raise_if_error(flag)
 # Guard budget before activation/weight workspace can be allocated.
 k.max_partial_bytes=1;k.quantize_input=lambda *a,**kw:pytest.fail('budget must precede quantization')
 with pytest.raises(ReferenceArithmeticError,match='workspace'):grouped(k,x,ws,split_k=8)
