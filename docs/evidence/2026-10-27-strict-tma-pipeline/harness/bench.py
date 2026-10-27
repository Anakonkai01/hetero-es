"""Same B22 projections, matched warm and explicit L2-evicted CUDA graph timings; no decoder gain claim."""
import argparse,hashlib,json,os,statistics,time
from pathlib import Path
import torch
from heteroes.eval import integer_cuda as ic
from heteroes.eval import strict_cuda as sc
from tma_mma import TmaMma
from tensor_map import maps
p=argparse.ArgumentParser();p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert a.gpu and os.environ.get('HETEROES_GPU_ACCEPTANCE')=='1' and not a.out.exists()
k=ic.IntegerCudaKernels('cuda',magnitude_bits=22);gen=torch.Generator(device='cuda').manual_seed(111);evict=torch.zeros(128*1024**2//4,device='cuda')
report={'status':'running','gpu':torch.cuda.get_device_name(),'baseIdentity':k.identity(),'implementation':'unselected_tma_projection_v1','sourceHashes':{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ('tma_mma.py','pipeline_copy.py','tensor_map.py','audit.py')},'cases':[],'limits':__doc__+' Core timings reuse descriptors; descriptor preparation is reported separately and not asserted free.'}
def timing(call,cold):
    call();torch.cuda.synchronize();graph=torch.cuda.CUDAGraph()
    if not cold:
      with torch.cuda.graph(graph):
        for _ in range(8):call()
      samples=[]
      for _ in range(9):
        first,last=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
        first.record();graph.replay();last.record();last.synchronize();samples.append(first.elapsed_time(last)*1000/8)
      return samples
    pairs=[(torch.cuda.Event(enable_timing=True,external=True),torch.cuda.Event(enable_timing=True,external=True)) for _ in range(8)]
    for first,last in pairs:first.record();last.record()
    torch.cuda.synchronize()
    with torch.cuda.graph(graph):
      for first,last in pairs:evict.add_(1.);first.record();call();last.record()
    samples=[]
    for _ in range(9):
      graph.replay();pairs[-1][1].synchronize();samples.extend(first.elapsed_time(last)*1000 for first,last in pairs)
    return samples
for rows,width,outputs,split,columns in ((888,896,4864,1,64),(888,4864,896,1,64),(32,896,9728,2,32),(32,4864,896,7,32),(32,896,1152,5,32),(32,896,896,7,32)):
    x=torch.randn(rows,width,device='cuda',generator=gen);w=(torch.randn(outputs,width,device='cuda',generator=gen)*.03).half()
    k._begin_request([w]);flag=k.new_error_flag();prepared=k.quantize_input(x,_packed=True,error_flag=flag);ew=k._weight_exponents(w,flag)
    def base():return k._linear(x,w,row_tile=32,split_k=split,implementation='mma',prepared=prepared,stream_columns=columns,error_flag=flag)
    expected=base();variants=[('base',base,None,None)]
    configs=[(2,3),(3,2)] if columns==64 else [(2,0),(3,0),(2,4)]
    for stages,resident in configs:
      c=TmaMma(width,columns,split,stages,resident)
      started=time.perf_counter();desc=maps(c.k,w,prepared[0],rows,width,columns);torch.cuda.synchronize();setup=time.perf_counter()-started
      def run(c=c,desc=desc):return c.project(prepared,w,ew,flag,descriptors=desc)
      assert torch.equal(run().view(torch.int32),expected.view(torch.int32)) and flag.item()==0
      variants.append((f'tma-st{stages}-r{resident}',run,c,setup))
    variants.append(('base-repeat',base,None,None));item={'rows':rows,'width':width,'outputs':outputs,'split':split,'columns':columns,'variants':[]}
    for label,call,c,setup in variants:
      entry={'label':label,'descriptorSetupSeconds':setup}
      if c:
        fn=c.functions['tma_stream'];attr=c.k._driver.CUfunction_attribute
        entry.update(registers=sc._check(c.k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_NUM_REGS,fn)),localBytes=sc._check(c.k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_LOCAL_SIZE_BYTES,fn)),sharedBytes=sc._check(c.k._driver.cuFuncGetAttribute(attr.CU_FUNC_ATTRIBUTE_SHARED_SIZE_BYTES,fn)),residentCtas=sc._check(c.k._driver.cuOccupancyMaxActiveBlocksPerMultiprocessor(fn,128,0)),build=c.k._builds[c.name])
      for cold in (False,True):
        samples=timing(call,cold);entry['cold' if cold else 'warm']={'microseconds':samples,'median':statistics.median(samples)}
      print(rows,width,outputs,label,'warm',round(entry['warm']['median'],2),'cold',round(entry['cold']['median'],2),'CTAs',entry.get('residentCtas'),'regs',entry.get('registers'),flush=True)
      item['variants'].append(entry)
    assert flag.item()==0;report['cases'].append(item);k._end_request()
report['status']='ok'
with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
