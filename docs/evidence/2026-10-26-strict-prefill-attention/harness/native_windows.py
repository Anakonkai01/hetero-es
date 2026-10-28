"""Explicitly authorized native Windows GPU check of streamed/grouped/fused B22 projections (same 3060 as WSL2).

Source tests, trained Qwen tile-vs-stream parity (parent/canonical ±/restored, chat + real EOS), then ABAB
whole-generation timing of base 48547ba3 vs new in separate processes. No managed lifecycle, installer or
universal qualification."""
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,tarfile,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--source-sha',required=True);a=p.parse_args()
if sys.platform!='win32' or not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':p.error('Native Windows and explicit GPU opt-in required')
root=Path.home()/'.cache'/'heteroes-native-strict-20261025-01';archive=root/'source-codex-prefill-01.tar.gz';stage=root/'stage-codex-prefill-01'
out=root/'codex-prefill-01';assert Path(sys.prefix).resolve()==(root/'venv').resolve()
report={'status':'running','hardwareQualified':False,'platform':platform.platform(),'python':sys.version,'executable':sys.executable,
 'limits':'Native source tests, finite trained Qwen tile-vs-stream comparison and first native ABAB timing. '
          'No managed lifecycle, installer or universal qualification.'}
started=time.perf_counter();handles=[]
try:
 digest=hashlib.sha256(archive.read_bytes()).hexdigest();assert digest==a.source_sha
 stage.mkdir(exist_ok=False);out.mkdir(exist_ok=False)
 with tarfile.open(archive)as t:t.extractall(stage,filter='data')
 manifest=json.loads((stage/'source-manifest-01.json').read_text(encoding='utf-8'))
 for name,expected in manifest['files'].items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==expected,name
 report.update(sourceArchiveSha256=digest,sourceManifestEqual=True,sourceFileCount=len(manifest['files']),commit=(stage/'new/COMMIT').read_text().strip())
 site=Path(sys.prefix)/'Lib/site-packages';dirs=sorted({x.parent for x in site.rglob('nvrtc*.dll')}|{x.parent for x in site.rglob('nvdisasm.exe')})
 for directory in dirs:handles.append(os.add_dll_directory(str(directory)))
 os.environ['PATH']=os.pathsep.join(map(str,dirs))+os.pathsep+os.environ.get('PATH','')
 os.environ['PYTHONNOUSERSITE']='1';os.environ['CUDA_VISIBLE_DEVICES']='0'
 new=stage/'new'
 os.environ['PYTHONPATH']=os.pathsep.join([str(new/'src'),str(new/'tests/eval'),str(new/'scripts')])
 os.chdir(new);sys.path[:0]=[str(new/'src'),str(new/'tests/eval')]
 import torch,transformers,pytest
 from cuda.bindings import nvrtc
 report.update(torch=torch.__version__,transformers=transformers.__version__,cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(),cc=list(torch.cuda.get_device_capability()),nvrtcResult=list(map(int,nvrtc.nvrtcVersion())),nvdisasm=shutil.which('nvdisasm'))
 if not report['nvdisasm']:raise RuntimeError('Native SASS auditor unavailable')
 tests=['tests/eval/'+n+'.py'for n in ('test_integer_stream','test_strict_decode_pipeline','test_integer_decoder','test_integer_group','test_integer_packed_input','test_integer_cuda','test_strict_decode_graph','test_strict_cuda','test_strict_packed','test_strict_attention_split','test_strict_attention_prefill','test_integer_fused_finish','test_fp16_decoder_cuda','test_qwen2_strict_cuda')]
 result=pytest.main(['-q','-p','no:cacheprovider',*tests]);report['pytestExitCode']=int(result)
 if result:raise RuntimeError('Native suite failed')
 torch.cuda.empty_cache()
 command=[sys.executable,'-B',str(stage/'probe_native_frozen_eos.py'),'--gpu','--eos-control',str(stage/'eos-control-01.json'),'--model-name','qwen','--model-path',str(root/'models-prefetch-01/qwen'),'--chat-workload',str(stage/'workload-chat-01.json'),'--out',str(out/'qwen-parity-native-01.json')]
 result=subprocess.run(command);report['trainedQwenParityExitCode']=result.returncode
 if result.returncode:raise RuntimeError('Native trained Qwen parity failed')
 report['bench']=[]
 for r in ('01','02'):
  for v in ('base','new'):
   env={**os.environ,'PYTHONPATH':str(stage/v/'src')}
   command=[sys.executable,'-B',str(stage/'bench_single.py'),'--gpu','--model','qwen','--models-root',str(root/'models-prefetch-01'),'--benchmark',str(new/'scripts/benchmark_inference.py'),'--probe',str(new/'scripts/probe_strict_backend.py'),'--workload',str(stage/'workload-chat-01.json'),'--label',v,'--out',str(out/f'single-qwen-{v}-native-{r}.json')]
   result=subprocess.run(command,env=env,cwd=str(stage));report['bench'].append({'label':v,'round':r,'exitCode':result.returncode})
   if result.returncode:raise RuntimeError('Native timing failed')
 for name,expected in manifest['files'].items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==expected,name
 report.update(status='ok',sourceManifestUnchangedAfter=True)
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
report['wallSeconds']=time.perf_counter()-started
with (root/'codex-prefill-native-run-01.json').open('x',encoding='utf-8')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'wallSeconds':report['wallSeconds'],'error':report.get('error')}),flush=True);raise SystemExit(report['status']!='ok')
