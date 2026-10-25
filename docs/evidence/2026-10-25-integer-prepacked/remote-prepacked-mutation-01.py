import subprocess,shlex,tarfile
from pathlib import Path
host='heheboiz@100.108.195.50';stage='/tmp/heteroes-integer-prepacked-selected-20261025-01';base=Path('.scratch/strict-integer-20261025');b=Path('docs/evidence/2026-10-25-integer-prepacked');cfg='/home/pc5070ti/.ssh/config';ssh=['ssh','-F',cfg,'-o','BatchMode=yes',host];scp=['scp','-F',cfg,'-o','BatchMode=yes'];python='/home/heheboiz/.local/share/heteroes-worker/runtimes/bf28fa656ad4/python/bin/python3'
for local,remote in [('scripts/mutation-check.py','mutation-check.py'),(str(b/'mutants-01.json'),'mutants-01.json'),(str(base/'probe_pinned_integer_families.py'),'probe_pinned_integer_families.py')]:subprocess.run(scp+[local,host+':'+stage+'/'+remote],check=True)
with tarfile.open(base/'prepacked-selected-fixtures-01.tar.gz','x:gz')as t:t.add(base/'native-stage-prepacked-01/fixtures',arcname='fixtures')
with (base/'prepacked-selected-fixtures-01.tar.gz').open('rb')as f:subprocess.run(ssh+['tar xzf - -C '+shlex.quote(stage)],stdin=f,check=True)
deps='/tmp/heteroes-integer-decode-plan-20261025-01/testdeps';test=shlex.join([python,'-m','pytest','-xq','tests/eval/test_integer_packed_input.py','tests/eval/test_integer_cuda.py','-k','packed_planes or narrow_graph or odd_shapes_tails'])
args=[python,'mutation-check.py','--repo','.','--copy','src','--copy','tests/eval/test_integer_packed_input.py','--copy','tests/eval/test_integer_cuda.py','--env','PYTHONPATH=src:'+deps,'--env','HETEROES_GPU_ACCEPTANCE=1','--env','CUDA_VISIBLE_DEVICES=0','--test',test,'--mutants','mutants-01.json']
r=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && '+shlex.join(args)])
if r.returncode:raise SystemExit(r.returncode)
out='linux-pinned-families-01.json';args=[python,'probe_pinned_integer_families.py','--gpu','--fixtures','fixtures','--out',out]
r=subprocess.run(ssh+['cd '+shlex.quote(stage)+' && HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=src:tests/eval:'+deps+' '+shlex.join(args)]);subprocess.run(scp+[host+':'+stage+'/'+out,str(b/out)],check=True);raise SystemExit(r.returncode)
