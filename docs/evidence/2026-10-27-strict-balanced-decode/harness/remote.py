"""Finite ABAB residency-plan control on 3060 WSL2, separate from final qualification."""
import hashlib,io,json,subprocess,tarfile
from pathlib import Path
repo=Path.cwd();out=repo/'docs/evidence/2026-10-27-strict-balanced-decode/raw'
files={}
for v,src in [('base','.scratch/codex-20261027-bound/stage/new/src'),('new','.scratch/codex-20261027-balanced/src')]:
 for p in (repo/src).rglob('*.py'):files[f'{v}/src/'+str(p.relative_to(repo/src))]=p.read_bytes()
for name,path in [('bench.py','docs/evidence/2026-10-26-strict-prefill-attention/harness/bench_single.py'),('benchmark.py','runtime/scripts/benchmark_inference.py'),('probe.py','runtime/scripts/probe_strict_backend.py'),('workload.json','docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json')]:files[name]=(repo/path).read_bytes()
script='''#!/bin/bash
set -euo pipefail
export HETEROES_GPU_ACCEPTANCE=1 PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib
PY=/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12
for r in a b; do
 for v in base new; do
  PYTHONPATH="$v/src" "$PY" bench.py --gpu --model qwen --models-root /home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models --benchmark benchmark.py --probe probe.py --workload workload.json --label "$v" --out "single-qwen-$v-3060-01$r.json" > "single-qwen-$v-3060-01$r.log" 2>&1
 done
done
'''
files['run.sh']=script.encode()
manifest={n:hashlib.sha256(v).hexdigest() for n,v in sorted(files.items())}
files['manifest.json']=json.dumps(manifest,indent=2).encode()
(out/'remote-manifest-01.json').open('xb').write(files['manifest.json'])
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as t:
 for n,d in sorted(files.items()):
  i=tarfile.TarInfo(n);i.size=len(d);t.addfile(i,io.BytesIO(d))
ssh=['ssh','-F','/home/pc5070ti/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=8','thao_nguyen@100.92.20.58'];stage='/tmp/heteroes-balanced-20261027-01'
subprocess.run(ssh+[f'mkdir {stage} && tar -xzf - -C {stage}'],input=buf.getvalue(),check=True)
verify="python3 -c 'import hashlib,json,pathlib; p=pathlib.Path(\".\"); assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in json.loads((p/\"manifest.json\").read_text()).items())'"
with (out/'remote-launch-01.log').open('x') as log:r=subprocess.run(ssh+[f'cd {stage} && {verify} && bash run.sh && {verify}'],stdout=log,stderr=subprocess.STDOUT)
with (out/'remote-receipts-01.tar.gz').open('xb') as f:subprocess.run(ssh+[f'cd {stage} && tar -czf - --no-recursion *.log *.json'],stdout=f,check=True)
with tarfile.open(out/'remote-receipts-01.tar.gz') as t:t.extractall(out/'3060-01',filter='data')
raise SystemExit(r.returncode)
