"""Matched integer kernels with exact CUDA-event intervals; cold tests evict L2 outside the timed interval."""
import argparse,hashlib,json,os,statistics
from pathlib import Path
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import strict_cuda as sc
from native_input import NativeInput
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
k=IntegerCudaKernels('cuda',magnitude_bits=22);gen=torch.Generator(device='cuda').manual_seed(93);evict=torch.zeros(128*1024**2//4,device='cuda')
report={'status':'running','gpu':torch.cuda.get_device_name(),'identity':k.identity(),'evictionBytes':evict.numel()*4,'sourceSha256':hashlib.sha256(Path(__file__).with_name('native_input.py').read_bytes()).hexdigest(),'cases':[],'limits':__doc__+' Operator screening only; no whole-generation or platform acceptance.'}
def timing(call,cold):
    call();torch.cuda.synchronize();graph=torch.cuda.CUDAGraph()
    pairs=[(torch.cuda.Event(enable_timing=True,external=True),torch.cuda.Event(enable_timing=True,external=True)) for _ in range(8)]
    # Initialize external CUDA events before capture; they will be recorded again on each graph replay.
    for start,end in pairs:start.record();end.record()
    torch.cuda.synchronize()
    with torch.cuda.graph(graph):
      for start,end in pairs:
        if cold:evict.add_(1.)
        start.record();call();end.record()
    times=[]
    for _ in range(9):
      graph.replay();pairs[-1][1].synchronize()
      times.append([start.elapsed_time(end)*1000 for start,end in pairs])
    return times
for rows,width,outputs,split,columns in ((888,896,4864,1,64),(888,4864,896,1,64),(32,896,9728,2,32),(32,4864,896,7,32),(32,896,1152,5,32),(32,896,896,7,32)):
    x=torch.randn(rows,width,device='cuda',generator=gen);w=(torch.randn(outputs,width,device='cuda',generator=gen)*.03).half()
    k._begin_request([w]);flag=k.new_error_flag();prepared=k.quantize_input(x,_packed=True,error_flag=flag);ew=k._weight_exponents(w,flag)
    def base():return k._linear(x,w,row_tile=32,split_k=split,implementation='mma',prepared=prepared,stream_columns=columns,error_flag=flag)
    expected=base();variants=[('base',base,None)]
    for resident in (0,4):
      candidate=NativeInput(k,width,columns,split,resident)
      native_prepared=candidate.pack(prepared)
      def run(candidate=candidate):return candidate.project(prepared,w,ew,flag)
      def core(candidate=candidate,native_prepared=native_prepared):return candidate.project(native_prepared,w,ew,flag,native=True)
      assert torch.equal(run().view(torch.int32),expected.view(torch.int32))
      assert torch.equal(core().view(torch.int32),expected.view(torch.int32))
      variants.append((f'native-input-r{resident}-pack-and-core',run,candidate))
      variants.append((f'native-input-r{resident}-core-only',core,candidate))
    variants.append(('base-repeat',base,None));case={'rows':rows,'width':width,'outputs':outputs,'split':split,'columns':columns,'variants':[]}
    for label,call,candidate in variants:
      item={'label':label}
      if candidate:
        fn=candidate.functions['integer_stream'];attr=k._driver.CUfunction_attribute
        item.update(registers=sc._check(k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_NUM_REGS,fn)),localBytes=sc._check(k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_LOCAL_SIZE_BYTES,fn)),sharedBytes=sc._check(k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES,fn)),residentCtas=sc._check(k._driver.cuOccupancyMaxActiveBlocksPerMultiprocessor(fn,128,0)))
      for cold in (False,True):
        values=timing(call,cold);flat=[v for row in values for v in row];item['cold' if cold else 'warm']={'microseconds':values,'median':statistics.median(flat)}
      print(rows,width,outputs,label,'warm',round(item['warm']['median'],2),'cold',round(item['cold']['median'],2),item.get('residentCtas'),flush=True)
      case['variants'].append(item)
    assert int(flag.item())==0;report['cases'].append(case);k._end_request()
report['status']='ok';report['builds']=k._builds
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
