"""Serialize selected WSL2 checks and native Windows checks on the same physical GPU."""
import base64
import hashlib
from pathlib import Path
import shlex
import subprocess

root = Path('.scratch/strict-prefetch-20261026')
ssh = ['ssh', '-F', '/home/pc5070ti/.ssh/config', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
       'thao_nguyen@100.92.20.58']
stage = '/tmp/heteroes-strict-prefetch-20261026-01/selected-02'
env = ('HETEROES_GPU_ACCEPTANCE=1 LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib '
       'PYTHONPATH=src:.:/tmp/heteroes-strict-integer-20261025-02/testdeps '
       '/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12')
commands = ['set -e', 'mkdir '+stage,
            'tar -xzf /tmp/heteroes-strict-prefetch-20261026-01/selected-source-02.tar.gz -C '+stage,
            'cd '+stage,
            env+" -m pytest -q tests/eval/test_integer_cuda.py -k 'destination_has_explicit or paired_weight_reads or prefetched_tiles_replay' > aligned-gpu-3060-02.log 2>&1"]
for model in ('qwen', 'smol', 'tiny'):
    commands.append(env+' bench_selected.py --gpu --model '+model+
                    ' --models-root /home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models'
                    ' --benchmark benchmark_inference.py --out '+model+'-selected-3060-02.json > '+model+'-selected-3060-02.log 2>&1')
for model in ('qwen', 'smol', 'tiny'):
    commands.append(env+' probe_selected_candidates.py --gpu --model-path '
                    '/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models/'+model+
                    ' --integer-bits 22 --out '+model+'-candidates-3060-02.json > '+model+'-candidates-3060-02.log 2>&1')
commands.append(env+' archive_audits.py --gpu --out audits-3060-02 > audits-3060-02.log 2>&1')
print('WSL2 final checks started', flush=True)
subprocess.run(ssh+['\n'.join(commands)], check=True)
print('WSL2 final checks completed; native Windows starts next', flush=True)
code=(root/'native_windows_run_prefetch_02.py').read_bytes()
sha=hashlib.sha256((root/'selected-source-02.tar.gz').read_bytes()).hexdigest()
pycode="exec(__import__('base64').b64decode('"+base64.b64encode(code).decode()+"'))"
python=r'C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\venv\Scripts\python.exe'
script='$env:HETEROES_GPU_ACCEPTANCE="1"; $ProgressPreference="SilentlyContinue"; & \''+python+'\' -I -B -c "'+pycode+'" --gpu --source-sha '+sha+'; exit $LASTEXITCODE'
encoded=base64.b64encode(script.encode('utf-16-le')).decode()
cmd='/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -NonInteractive -EncodedCommand '+encoded
subprocess.run(ssh+[cmd], check=True)
print('Native Windows final checks completed', flush=True)
