"""Active-request integer projection sweep: bounded geometry choices, no per-token metadata rescan."""
import argparse,hashlib,json,os,statistics
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh output required')
import torch
from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval import integer_reference as reference
context=torch.empty(1,device='cuda');k=IntegerCudaKernels('cuda',magnitude_bits=22)
report={'status':'running','hardwareQualified':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'gpu':torch.cuda.get_device_name(),'multiprocessors':torch.cuda.get_device_properties(0).multi_processor_count,'cases':[],
 'limits':'Synthetic projections under refreshed active-request metadata; CUDA event medians exclude host and request-entry metadata. All variant output bits compared; sampled CPU oracle. Not model throughput, quality or qualification.'}
def measure(run):
 run();torch.cuda.synchronize();graph=torch.cuda.CUDAGraph()
 with torch.cuda.graph(graph):
  for _ in range(10):run()
 for _ in range(2):graph.replay()
 torch.cuda.synchronize();ms=[]
 for _ in range(3):
  start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True);start.record();graph.replay();end.record();end.synchronize();ms.append(start.elapsed_time(end)/10)
 return ms
try:
 for width,outputs in [(768,256),(768,4096),(960,320),(960,2560),(960,49152),(1024,512),(1024,4096),(1024,65536),(1536,256),(1536,4096),(2048,256),(2048,2048),(2048,5632),(2048,11008),(2048,32000),(2560,960),(3072,1024),(4096,4096),(5632,2048),(8192,1024)]:
  gen=torch.Generator().manual_seed(width+outputs);w=(torch.randn(outputs,width,generator=gen)*.02).half().cuda();x=torch.randn(128,width,generator=gen).cuda();k._begin_request([w])
  try:
   for rows in (64,128):
    value=x[:rows];expected=k.linear(value,w);oracle=reference.linear(value[:1].cpu(),w[:3].cpu(),magnitude_bits=22)
    assert torch.equal(expected[:1,:3].cpu().contiguous().view(torch.int32),oracle.view(torch.int32));flag=k.new_error_flag()
    options=[]
    for tile in (32,64,128):
     for warps in (4,):
      blocks=((outputs+8*warps-1)//(8*warps))*((rows+tile-1)//tile);split=1
      while split<8 and blocks*split<8*report['multiprocessors']:split*=2
      while split>1 and split*rows*outputs*8>k.max_partial_bytes:split//=2
      options.extend([('mma',1,tile,warps),('mma',split,tile,warps)])
    options=list(dict.fromkeys(options))
    for mode,split,tile,warps in options:
     if split>1 and split*rows*outputs*8>k.max_partial_bytes:continue
     def run():return k.linear(value,w,error_flag=flag,implementation=mode,split_k=split,row_tile=tile,warps=warps)
     actual=run();k.raise_if_error(flag);assert torch.equal(actual.view(torch.int32),expected.view(torch.int32))
     ms=measure(run);k.raise_if_error(flag)
     case={'width':width,'outputs':outputs,'rows':rows,'mode':mode,'splitK':split,'rowTile':tile,'warps':warps,'eventMs':ms,'medianEventMs':statistics.median(ms),'bitsEqual':True};fn=k._integer_functions(width,False,tile,warps,split)['integer_linear'];case['functionResources']={name:int(k._driver.cuFuncGetAttribute(getattr(k._driver.CUfunction_attribute,'CU_FUNC_ATTRIBUTE_'+name),fn)[1])for name in ('NUM_REGS','LOCAL_SIZE_BYTES','SHARED_SIZE_BYTES')};report['cases'].append(case)
    best=min([c for c in report['cases']if (c['width'],c['outputs'],c['rows'])==(width,outputs,rows)],key=lambda c:c['medianEventMs']);print(json.dumps(best),flush=True)
  finally:k._end_request();torch.cuda.synchronize()
  del w,x,expected,actual
 report['identity']=k.identity();report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
