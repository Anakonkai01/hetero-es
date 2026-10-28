import subprocess,shlex
from pathlib import Path
base=Path('.scratch/strict-integer-20261025');b=Path('docs/evidence/2026-10-25-integer-prepacked');host='thao_nguyen@100.92.20.58';stage='/tmp/heteroes-integer-prepacked-selected-20261025-01';cfg='/home/pc5070ti/.ssh/config';ssh=['ssh','-F',cfg,'-o','BatchMode=yes',host];scp=['scp','-F',cfg,'-o','BatchMode=yes'];python='/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12'
subprocess.run(ssh+['mkdir '+shlex.quote(stage)],check=True)
with (base/'prepacked-selected-source-01.tar.gz').open('rb')as f:subprocess.run(ssh+['tar xzf - -C '+shlex.quote(stage)],stdin=f,check=True)
models={'smol':'/home/thao_nguyen/.cache/heteroes-strict-models-20261025/SmolLM2-360M-Instruct/a10cc1512eabd3dde888204e902eca88bddb4951','qwen':'/home/thao_nguyen/.local/share/heteroes-c4-cpu/models/7ae557604adf67be50417f59c2c2f167def9a775'}
env='LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=src:/tmp/heteroes-integer-decode-plan-20261025-01/testdeps '
for name,model in models.items():
 for kind in ('bench','quality'):
  out=f'selected-{kind}-{name}-thao-01.json';assert not(b/out).exists();args=['scripts/benchmark_inference.py','--engine','strict-integer','--integer-bits','22','--graph-max-bytes','4294967296']if kind=='bench'else['scripts/probe_integer_decoder.py'];args+=['--gpu','--model-path',model,'--out',out]
  r=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && '+env+shlex.join([python,*args])]);subprocess.run(scp+[host+':'+stage+'/'+out,str(b/out)],check=True)
  if r.returncode:raise SystemExit(r.returncode)
