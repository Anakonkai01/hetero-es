"""Profile a warmed NEW integer graph on a trained local model, keeping CUDA and wall scopes distinct."""
import argparse,hashlib,importlib.util,json,os,statistics,time
from pathlib import Path
from types import SimpleNamespace
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--model-path',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1' or a.out.exists():p.error('Need GPU opt-in and fresh evidence')
import torch
spec=importlib.util.spec_from_file_location('bench',Path('runtime/scripts/benchmark_inference.py'));bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
report={'status':'running','hardwareQualified':False,'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'environment':{},'cases':[],
 'limits':'One trained parent; same fixed-length common benchmark. Profiler overhead affects events. Kernel-duration sum includes prefill, metadata and replay, not only decode. Unprofiled synchronized wall median is separate. No serving, ES, quality or universal acceptance.'}
try:
 args=SimpleNamespace(model_path=a.model_path,engine='strict-integer',integer_bits=22,max_context=512,max_new_tokens=32,graph_max_bytes=4*1024**3)
 engine,prompts,run=bench.load_engine(args,report)
 for batch in (1,8,32):
  rows=[prompts[i%len(prompts)]for i in range(batch)];run(rows);durations=[]
  for _ in range(3):
   torch.cuda.synchronize();begin=time.perf_counter();expected=run(rows);torch.cuda.synchronize();durations.append(time.perf_counter()-begin)
  with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA])as prof:
   actual=run(rows);torch.cuda.synchronize()
  assert actual==expected
  cuda={}
  for e in prof.events():
   if str(e.device_type)=='DeviceType.CUDA':
    item=cuda.setdefault(e.name,{'calls':0,'totalUs':0});item['calls']+=1;item['totalUs']+=e.time_range.elapsed_us()
  assert cuda,'No CUDA events captured; cannot claim kernel attribution'
  groups={}
  for name,item in cuda.items():
   if 'integer_linear' in name or 'integer_simt'in name or 'integer_finish'in name:group='integer_projection'
   elif 'integer_input'in name:group='activation_quantization'
   elif 'integer_weights'in name:group='weight_metadata'
   elif 'attention'in name:group='attention'
   else:group='other_including_copies'
   g=groups.setdefault(group,{'calls':0,'totalUs':0});g['calls']+=item['calls'];g['totalUs']+=item['totalUs']
  total=sum(v['totalUs']for v in groups.values())
  report['cases'].append({'batch':batch,'wallSeconds':durations,'medianWallSeconds':statistics.median(durations),'tokensPerSecond':32*batch/statistics.median(durations),'totalCudaEventUs':total,'groups':{k:{**v,'fraction':v['totalUs']/total}for k,v in groups.items()},'cuda':sorted([dict(name=k,**v)for k,v in cuda.items()],key=lambda c:-c['totalUs'])})
 report['kernelIdentity']=engine.kernel_identity();report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
with a.out.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
