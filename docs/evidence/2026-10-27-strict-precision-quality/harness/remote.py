"""Run the already defined B14/B22 contracts on the 3060 with the frozen 267ba0b5 implementation."""
import io
from pathlib import Path
import shlex
import subprocess
import tarfile
repo=Path.cwd();out=repo/'docs/evidence/2026-10-27-strict-precision-quality/raw'
files={str(p.relative_to(repo/'.scratch/codex-20261027-bound/stage/new')):p.read_bytes() for p in (repo/'.scratch/codex-20261027-bound/stage/new/src').rglob('*.py')}
files['probe.py']=(repo/'docs/evidence/2026-10-27-strict-precision-quality/harness/probe.py').read_bytes()
files['workload.json']=(repo/'docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_bytes()
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
    for name,data in files.items():
        item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
ssh=['ssh','-F','/home/pc5070ti/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=8','thao_nguyen@100.92.20.58']
stage='/tmp/heteroes-precision-quality-20261027-01'
subprocess.run(ssh+[f'mkdir {stage} && tar -xzf - -C {stage}'],input=buf.getvalue(),check=True)
command=f'cd {stage} && HETEROES_GPU_ACCEPTANCE=1 LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib PYTHONPATH=src /home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12 probe.py --gpu --model-path /home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models/qwen --workload workload.json --out quality-3060-01.json > quality-3060-01.log 2>&1'
with (out/'remote-launch-01.log').open('x') as log:result=subprocess.run(ssh+[command],stdout=log,stderr=subprocess.STDOUT)
for name in ('quality-3060-01.json','quality-3060-01.log'):
    with (out/name).open('xb') as f:subprocess.run(ssh+[f'cat {stage}/{name}'],stdout=f,check=True)
raise SystemExit(result.returncode)
