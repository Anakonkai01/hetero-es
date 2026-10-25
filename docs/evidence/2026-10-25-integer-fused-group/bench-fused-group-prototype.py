"""Trained source-guided group-launch experiment. Runtime prototype identity is explicit and unselected."""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
from types import SimpleNamespace
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--model-path',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('GPU opt-in and fresh output required')
import torch
from integer_grouped_prototype import grouped
module_path=Path(__file__).with_name('integer_grouped_prototype.py')
spec=importlib.util.spec_from_file_location('bench',Path('runtime/scripts/benchmark_inference.py'));bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
report={'status':'running','hardwareQualified':False,'selected':False,'baselineSourceCommit':'97f62431','benchmarkSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'groupedPrototypeSourceSha256':hashlib.sha256(module_path.read_bytes()).hexdigest(),'environment':{},'cases':[],
 'limits':'Same parent, fixed eight-prompt pool, native/segmented decode launches in one process. Supplementary prototype source identity recorded; no default/source promotion, quality, trained cross-device, native Windows or managed qualification. No concatenated/quantized full weight copy.'}
try:
 args=SimpleNamespace(model_path=a.model_path,engine='strict-integer',integer_bits=22,max_context=512,max_new_tokens=32,graph_max_bytes=4*1024**3)
 engine,prompts,run=bench.load_engine(args,report);old=engine._decode_project_many;state={'enabled':False,'groups':0}
 def project(value,modules,flag):
  if not state['enabled']:return old(value,modules,flag)
  state['groups']+=1
  return grouped(engine.kernels,value,tuple(m.weight for m in modules),tuple(getattr(m,'bias',None)for m in modules),error_flag=flag,target_ctas_per_sm=engine.decode_target_ctas_per_sm)
 engine._decode_project_many=project
 for batch in (1,8,32):
  rows=[prompts[i%len(prompts)]for i in range(batch)];baseline=None
  for enabled in (False,True):
   engine.release_graph();state.update(enabled=enabled,groups=0);torch.cuda.reset_peak_memory_stats()
   result=bench.measure(run,rows,32,3,torch.cuda.synchronize);logits=hashlib.sha256(engine._session.last_logits.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
   if not enabled:baseline=(result['tokens'],logits)
   else:assert baseline==(result['tokens'],logits),(batch,'grouped token/logit mismatch')
   result.update(batch=batch,variant='segmented_group'if enabled else'separate',lastLogitsSha256=logits,tokensAndFinalLogitsEqualBaseline=True,peakAllocatedBytes=torch.cuda.max_memory_allocated(),groupCallsDuringCapture=state['groups'],admittedMetadataAndPartialBytes=engine._request_workspace_bytes(batch))
   report['cases'].append(result);print(json.dumps({key:result[key]for key in('batch','variant','tokensPerSecondTotal','peakAllocatedBytes')}),flush=True)
 engine.release_graph();report['kernelIdentity']=engine.kernel_identity();report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
