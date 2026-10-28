import subprocess,shlex,sys
from pathlib import Path
hosts={'thao':('thao_nguyen@100.92.20.58','/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12'),'quang':('quang@100.99.227.8','/home/quang/heteroes-venv/bin/python')};name=sys.argv[1];host,python=hosts[name];stage='/tmp/heteroes-attention-chunk8-20261025-01';base=Path('.scratch/strict-integer-20261025');b=Path('docs/evidence/2026-10-25-attention-tree');cfg='/home/pc5070ti/.ssh/config';ssh=['ssh','-F',cfg,'-o','BatchMode=yes',host];scp=['scp','-F',cfg,'-o','BatchMode=yes']
subprocess.run(ssh+['mkdir '+shlex.quote(stage)],check=True)
with (base/'attention-chunk8-feasibility-01.tar.gz').open('rb')as f:subprocess.run(ssh+['tar xzf - -C '+shlex.quote(stage)],stdin=f,check=True)
env='LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=src:tests/eval:/tmp/heteroes-integer-decode-plan-20261025-01/testdeps '
args=[python,'-m','pytest','-xq','test_attention_tree.py','test_attention_chunk.py','tests/eval/test_strict_cuda.py','tests/eval/test_strict_packed.py','-k','tree or attention'];r=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && '+env+shlex.join(args)])
if r.returncode:sys.exit(r.returncode)
out=f'resources-chunk8-{name}-01.json';args=[python,'probe_attention_resources.py','--gpu','--out',out];r=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && '+env+shlex.join(args)]);subprocess.run(scp+[host+':'+stage+'/'+out,str(b/out)],check=True)
if r.returncode:sys.exit(r.returncode)
if name=='thao':
 models={'smol':'/home/thao_nguyen/.cache/heteroes-strict-models-20261025/SmolLM2-360M-Instruct/a10cc1512eabd3dde888204e902eca88bddb4951','qwen':'/home/thao_nguyen/.local/share/heteroes-c4-cpu/models/7ae557604adf67be50417f59c2c2f167def9a775'}
 for label,model in models.items():
  for kind in ('bench','quality'):
   out=f'{kind}-chunk8-{label}-{name}-01.json';assert not(b/out).exists();args=['scripts/benchmark_inference.py','--engine','strict-integer','--integer-bits','22','--graph-max-bytes','4294967296']if kind=='bench'else['scripts/probe_integer_decoder.py'];args+=['--gpu','--model-path',model,'--out',out]
   r=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && '+env+shlex.join([python,*args])]);subprocess.run(scp+[host+':'+stage+'/'+out,str(b/out)],check=True)
   if r.returncode:sys.exit(r.returncode)
