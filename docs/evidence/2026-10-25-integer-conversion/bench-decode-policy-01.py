"""Trained-model feasibility of dimension/SM-based split-K ONLY inside captured decode; no source promotion."""
import argparse,collections,hashlib,importlib.util,json,os,statistics,time
from pathlib import Path
from types import SimpleNamespace
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--model-path',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh output required')
import torch
spec=importlib.util.spec_from_file_location('bench',Path('runtime/scripts/benchmark_inference.py'));bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
report={'status':'running','hardwareQualified':False,'selected':False,'sourceCommit':'eeb74c23','policySourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'environment':{},'cases':[],
 'limitations':'Parent only, fixed benchmark; runtime monkeypatch prototype adds decode geometry to the unchanged source identity. Record policy source/target separately. Exact final logit/token equality checked per batch. Unisolated host wall medians; no quality/managed/native acceptance.'}
try:
 args=SimpleNamespace(model_path=a.model_path,engine='strict-integer',integer_bits=22,max_context=512,max_new_tokens=32,graph_max_bytes=4*1024**3)
 engine,prompts,run=bench.load_engine(args,report);k=engine.kernels;sm=torch.cuda.get_device_properties(0).multi_processor_count
 state={'target':0,'decode':False,'capacity':1};seen=collections.Counter();original_core=engine._decode_core;original_linear=k._linear;original_workspace=engine._request_workspace_bytes
 shapes=collections.Counter((w.shape[1],w.shape[0])for w in engine._projection_weights())
 def plan(width,outputs,rows):
  tile=16 if rows<=16 else 32;mode='simt' if rows==1 else 'mma';split=1
  if rows>1 and width>=256 and state['target']:
   blocks=((outputs+31)//32)*((rows+tile-1)//tile)
   while split<8 and blocks*split<state['target']*sm:split*=2
   while split>1 and (split*rows*outputs*8>k.max_partial_bytes or split>(width+31)//32):split//=2
  return tile,mode,split
 def core(session):
  state['decode']=True
  try:return original_core(session)
  finally:state['decode']=False
 def linear(value,weight,bias=None,**kwargs):
  if state['decode'] and state['target']:
   width,outputs=weight.shape[1],weight.shape[0];rows=value.numel()//width;tile,mode,split=plan(width,outputs,rows)
   kwargs.update(row_tile=tile,implementation=mode,split_k=split);seen[(width,outputs,rows,split,tile)]+=1
  return original_linear(value,weight,bias,**kwargs)
 def extra_workspace():
  extra=0
  if state['target']:
   for (width,outputs),copies in shapes.items():
    maximum=0
    for rows in range(1,state['capacity']+1):
     _,_,split=plan(width,outputs,rows)
     if split>1:maximum=max(maximum,split*rows*outputs*8)
    extra+=copies*maximum
  return original_workspace()+extra
 engine._decode_core=core;k._linear=linear;engine._request_workspace_bytes=extra_workspace
 baseline={}
 for batch in (1,8,32):
  rows=[prompts[i%len(prompts)]for i in range(batch)];state['capacity']=batch
  for target in (0,2,8):
   engine.release_graph();state['target']=target;seen.clear();torch.cuda.reset_peak_memory_stats()
   result=bench.measure(run,rows,32,3,torch.cuda.synchronize)
   logits=hashlib.sha256(engine._session.last_logits.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
   if target==0:baseline[batch]=(result['tokens'],logits)
   else:assert baseline[batch]==(result['tokens'],logits),(batch,target)
   result.update(batch=batch,targetCtasPerSm=target,lastLogitsSha256=logits,tokensAndLogitsEqualBaseline=True,decodePartialAdmissionBoundBytes=extra_workspace()-original_workspace(),peakAllocatedBytes=torch.cuda.max_memory_allocated(),observedCapturePlans=[dict(width=w,outputs=n,rows=m,splitK=s,rowTile=t,calls=c)for(w,n,m,s,t),c in sorted(seen.items())])
   report['cases'].append(result);print(json.dumps({key:result[key]for key in('batch','targetCtasPerSm','tokensPerSecondTotal','decodePartialAdmissionBoundBytes')}),flush=True)
 engine.release_graph();report['kernelIdentity']=engine.kernel_identity();report['multiprocessors']=sm;report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
