"""Run an explicitly authorized native GPU suite in the isolated, pinned task environment."""
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,tarfile,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gpu',action='store_true');p.add_argument('--source-sha',required=True);a=p.parse_args()
if sys.platform!='win32' or not a.gpu or os.environ.get('HETEROES_GPU_ACCEPTANCE')!='1':p.error('Native Windows and explicit GPU opt-in required')
root=Path.home()/'.cache'/'heteroes-native-strict-20261025-01';archive=root/'source-prepacked-01.tar.gz';stage=root/'stage-prepacked-01'
assert Path(sys.prefix).resolve()==(root/'venv').resolve()
report={'status':'running','hardwareQualified':False,'sourceCommit':'1848d57c','platform':platform.platform(),'python':sys.version,'executable':sys.executable,'pid':os.getpid(),
 'limits':'Isolated native Python source tests and pinned tiny fixtures only; no trained quality/throughput, managed lifecycle, installer or universal qualification.'}
started=time.perf_counter();handles=[]
with (root/'prepacked-native-run-start-01.json').open('x',encoding='utf-8')as f:json.dump(report,f,indent=2);f.write('\n')
try:
 digest=hashlib.sha256(archive.read_bytes()).hexdigest();assert digest==a.source_sha
 stage.mkdir(exist_ok=False)
 with tarfile.open(archive)as t:t.extractall(stage,filter='data')
 manifest=json.loads((stage/'source-manifest-01.json').read_text(encoding='utf-8'))
 for name,expected in manifest['files'].items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==expected,name
 report.update(sourceArchiveSha256=digest,sourceManifestEqual=True,sourceFileCount=len(manifest['files']))
 site=Path(sys.prefix)/'Lib/site-packages';dirs=sorted({x.parent for x in site.rglob('nvrtc*.dll')}|{x.parent for x in site.rglob('nvdisasm.exe')})
 for directory in dirs:handles.append(os.add_dll_directory(str(directory)))
 os.environ['PATH']=os.pathsep.join(map(str,dirs))+os.pathsep+os.environ.get('PATH','')
 os.environ['PYTHONPATH']=os.pathsep.join([str(stage/'src'),str(stage/'tests/eval')]);os.environ['PYTHONNOUSERSITE']='1';os.environ['CUDA_VISIBLE_DEVICES']='0'
 os.chdir(stage);sys.path[:0]=[str(stage/'src'),str(stage/'tests/eval')]
 import torch,transformers,pytest
 from cuda.bindings import nvrtc
 report.update(torch=torch.__version__,transformers=transformers.__version__,pytest=pytest.__version__,cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(),cc=list(torch.cuda.get_device_capability()),nvrtcResult=list(map(int,nvrtc.nvrtcVersion())),nvdisasm=shutil.which('nvdisasm'))
 if not report['nvdisasm']:raise RuntimeError('Native SASS auditor unavailable')
 report['nvdisasmSha256']=hashlib.sha256(Path(report['nvdisasm']).read_bytes()).hexdigest()
 tests=['tests/eval/'+name+'.py'for name in ('test_integer_plan','test_benchmark_inference','test_integer_packed_input','test_integer_reference','test_integer_cuda','test_integer_decoder','test_integer_group','test_strict_cuda','test_strict_decode_cuda','test_strict_decode_graph','test_strict_packed','test_qwen2_strict_cuda','test_strict_decoder')]
 print(json.dumps({'phase':'native-tests','sourceFiles':len(manifest['files']),'gpu':report['gpu']}),flush=True)
 result=pytest.main(['-xq',*tests]);report['pytestExitCode']=int(result)
 if result:raise RuntimeError('Native selected suite failed')
 command=[sys.executable,'-B',str(stage/'probe_pinned_integer_families.py'),'--gpu','--fixtures',str(stage/'fixtures'),'--out',str(root/'prepacked-pinned-families-01.json')]
 result=subprocess.run(command);report['pinnedFixtureExitCode']=result.returncode
 if result.returncode:raise RuntimeError('Native pinned graph comparison failed')
 for name,expected in manifest['files'].items():assert hashlib.sha256((stage/name).read_bytes()).hexdigest()==expected,name
 report.update(status='ok',sourceManifestUnchangedAfter=True)
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
report['wallSeconds']=time.perf_counter()-started
with (root/'prepacked-native-run-01.json').open('x',encoding='utf-8')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'wallSeconds':report['wallSeconds'],'error':report.get('error')}),flush=True);raise SystemExit(report['status']!='ok')
