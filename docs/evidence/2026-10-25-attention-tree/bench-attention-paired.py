"""ABBA, same model/process, explicit old/new CUDA module routing; not a selected backend identity."""
import argparse,ast,hashlib,importlib.util,json,os,statistics
from pathlib import Path
from types import SimpleNamespace
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--model-path',type=Path,required=True);p.add_argument('--candidate-source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1'or a.out.exists():p.error('GPU opt-in and fresh output required')
import torch
from heteroes.eval import strict_cuda as sc
source=next(ast.literal_eval(n.value)for n in ast.parse(a.candidate_source.read_text()).body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='_OPS_SOURCE'for t in n.targets))
spec=importlib.util.spec_from_file_location('benchmark',Path('runtime/scripts/benchmark_inference.py'));bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
r={'status':'running','hardwareQualified':False,'selected':False,'baselineNumericCommit':'1848d57c','probeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'oldOpsSha256':hashlib.sha256(sc._OPS_SOURCE.encode()).hexdigest(),'newOpsSha256':hashlib.sha256(source.encode()).hexdigest(),'environment':{},'cases':[],'limits':'Runtime CUDA module override, ABBA within one process and one FP16 model; explicit supplemental source hashes. Fixed benchmark, unisolated device. No selected/default/managed/native/general quality claim.'}
try:
 args=SimpleNamespace(model_path=a.model_path,engine='strict-integer',integer_bits=22,max_context=512,max_new_tokens=32,graph_max_bytes=4*1024**3)
 engine,prompts,run=bench.load_engine(args,r);k=engine.kernels;header=''.join(f'#define {key} 0x{value:08x}u\n'for key,value in sc.reference_constants().items());entries=['strict_rms_norm','strict_add','strict_silu_mul','strict_rope','strict_attention']
 modules={label:k._compile('paired-'+label,header+code,entries,ptx_exact=sc.OPS_PTX_EXACT,sass_exact=sc.OPS_SASS_EXACT)for label,code in [('old',sc._OPS_SOURCE),('new',source)]};state={'variant':'old'};k._ops=lambda entry:modules[state['variant']][entry]
 for batch in(1,8,32):
  rows=[prompts[i%len(prompts)]for i in range(batch)];golden=None;observations=[]
  for variant in('old','new','new','old'):
   engine.release_graph();state['variant']=variant;torch.cuda.reset_peak_memory_stats();case=bench.measure(run,rows,32,3,torch.cuda.synchronize);logits=hashlib.sha256(engine._session.last_logits.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
   if golden is None:golden=(case['tokens'],logits)
   assert golden==(case['tokens'],logits)and case['repeatTokensEqual'],(batch,variant)
   case.update(variant=variant,lastLogitsSha256=logits,peakAllocatedBytes=torch.cuda.max_memory_allocated());observations.append(case)
  summaries={}
  for variant in('old','new'):
   seconds=[x for c in observations if c['variant']==variant for x in c['seconds']];summaries[variant]={'seconds':seconds,'medianSeconds':statistics.median(seconds),'tokensPerSecondTotal':batch*32/statistics.median(seconds)}
  ratio=summaries['new']['tokensPerSecondTotal']/summaries['old']['tokensPerSecondTotal'];r['cases'].append({'batch':batch,'observations':observations,'summary':summaries,'ratio':ratio,'tokensAndFinalLogitsEqual':True});print(json.dumps({'batch':batch,'old':summaries['old']['tokensPerSecondTotal'],'new':summaries['new']['tokensPerSecondTotal'],'ratio':ratio}),flush=True)
 engine.release_graph();r['kernelIdentity']=engine.kernel_identity();r['status']='ok'
except Exception as e:r.update(status='error',errorType=type(e).__name__,error=str(e))
with a.out.open('x')as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps({'status':r['status'],'error':r.get('error')}));raise SystemExit(r['status']!='ok')
