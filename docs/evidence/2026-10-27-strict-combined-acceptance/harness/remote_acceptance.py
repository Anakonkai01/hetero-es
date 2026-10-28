"""Frozen 0eb86cb9: full WSL suites, trained parity, ABAB; then full native suites/parity/ABAB.

Wait for the already running prefill-native check before using the same physical 3060.
Only fresh standalone cache directories are written. The live lab and device state are not accessed.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

REPO = Path.cwd()
OUT = REPO / 'docs/evidence/2026-10-27-strict-combined-acceptance/raw'
HERE = REPO / 'docs/evidence/2026-10-26-strict-prefill-attention/harness'
SSH = ['ssh', '-F', '/home/pc5070ti/.ssh/config', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'thao_nguyen@100.92.20.58']
ROOT = '/tmp/heteroes-codex-combined-20261027-01'
WIN = '/mnt/c/Users/Thao Nguyen/.cache/heteroes-native-strict-20261025-01'
STAGE = REPO / '.scratch/codex-20261027-combined/stage'
assert (STAGE / 'new/COMMIT').read_text().strip() == '0eb86cb948878fe430049882b80b3a5ad74730ba'
files = {str(p.relative_to(STAGE)): p.read_bytes() for p in STAGE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'SHA256SUMS'}
for name in ('probe_native_frozen_eos.py', 'frozen_eos.py', 'eos-control-01.json'):
    files[name] = (HERE / name).read_bytes()
code = (HERE / 'native_windows.py').read_text().replace('codex-prefill-01', 'codex-combined-01').replace('codex-prefill-native-run-01', 'codex-combined-native-run-01')
code = code.replace("'test_integer_stream',", "'test_integer_lm_head','test_integer_weights_batched','test_integer_stream',")
code = code.replace("'test_integer_stream',", "'test_integer_balanced_plan','test_integer_nonpower_split','test_strict_graph_host','test_integer_stream',")
files['native_windows_combined.py'] = code.encode()
(REPO / 'docs/evidence/2026-10-27-strict-combined-acceptance/harness/native_windows_combined.py').write_bytes(files['native_windows_combined.py'])
script = r'''#!/bin/bash
set -euo pipefail
export HETEROES_GPU_ACCEPTANCE=1 PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib
PY=/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12
DEPS=/tmp/heteroes-codex-testdeps-20261027-01
MODELS=/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models
"$PY" -c 'import json,hashlib,pathlib; p=pathlib.Path("."); m=json.loads((p/"source-manifest-01.json").read_text()); assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in m["files"].items())' > source-check-01.log 2>&1
(cd new && PYTHONPATH="src:$DEPS" "$PY" -m pytest -q -p no:cacheprovider tests/eval/test_strict_*.py tests/eval/test_integer_*.py tests/eval/test_fp16_decoder_cuda.py > ../tests-3060-01.log 2>&1)
for m in qwen smol tiny; do
  probe=probe_projection_parity.py
  extra=()
  if [ "$m" = qwen ]; then
    probe=probe_native_frozen_eos.py
    extra=(--chat-workload workload-chat-01.json --eos-control eos-control-01.json)
  fi
  PYTHONPATH=new/src:new/scripts "$PY" "$probe" --gpu --model-name "$m" --model-path "$MODELS/$m" "${extra[@]}" --out "$m-parity-3060-01.json" > "$m-parity-3060-01.log" 2>&1
done
for r in a b; do
  for v in base new; do
    PYTHONPATH="$v/src" "$PY" bench_single.py --gpu --model qwen --models-root "$MODELS" --benchmark new/scripts/benchmark_inference.py --probe new/scripts/probe_strict_backend.py --workload workload-chat-01.json --label "$v" --out "single-qwen-$v-3060-01$r.json" > "single-qwen-$v-3060-01$r.log" 2>&1
  done
done
"$PY" -c 'import json,hashlib,pathlib; p=pathlib.Path("."); m=json.loads((p/"source-manifest-01.json").read_text()); assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in m["files"].items())' > source-check-after-01.log 2>&1
echo WSL_DONE
'''
files['remote_combined.sh'] = script.encode()
manifest = {'commit': '0eb86cb948878fe430049882b80b3a5ad74730ba', 'base': (STAGE / 'base/COMMIT').read_text().strip(), 'files': {n: hashlib.sha256(v).hexdigest() for n,v in sorted(files.items())}}
files['source-manifest-01.json'] = json.dumps(manifest, indent=2).encode()
(OUT / 'remote-source-manifest-01.json').write_bytes(files['source-manifest-01.json'])
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w:gz') as packed:
    for name, data in sorted(files.items()):
        item = tarfile.TarInfo(name)
        item.size, item.mtime = len(data), 0
        packed.addfile(item, io.BytesIO(data))
archive = buffer.getvalue()
sha = hashlib.sha256(archive).hexdigest()
(OUT / 'remote-source-01.sha256').write_text(f'{sha}  source-codex-combined-01.tar.gz\n')
( REPO / '.scratch/codex-20261027-combined/remote-source-01.tar.gz').write_bytes(archive)
command = f'mkdir {shlex.quote(ROOT)} && tar -xzf - -C {shlex.quote(ROOT)}'
subprocess.run(SSH + [command], input=archive, check=True)
print('Frozen source staged', sha, flush=True)
command = f'while ! test -f {shlex.quote(WIN + "/codex-prefill-native-run-02.json")}; do sleep 5; done; cd {shlex.quote(ROOT)} && bash remote_combined.sh > remote-console-01.log 2>&1'
with (OUT / 'wsl-launch-01.log').open('x') as log:
    result = subprocess.run(SSH + [command], stdout=log, stderr=subprocess.STDOUT)
print('WSL exit', result.returncode, flush=True)
with (OUT / 'wsl-receipts-01.tar.gz').open('xb') as target:
    subprocess.run(SSH + [f'cd {shlex.quote(ROOT)} && tar -czf - --no-recursion *.log *.json'], stdout=target, check=True)
with tarfile.open(OUT / 'wsl-receipts-01.tar.gz') as source:
    source.extractall(OUT / '3060-wsl-01', filter='data')
if result.returncode:
    raise SystemExit('WSL acceptance failed; native check not started')
path = WIN + '/source-codex-combined-01.tar.gz'
subprocess.run(SSH + [f'test ! -e {shlex.quote(path)} && cat > {shlex.quote(path)} && sha256sum {shlex.quote(path)}'], input=archive, check=True)
pycode = "exec(__import__('base64').b64decode('" + base64.b64encode(code.encode()).decode() + "'))"
python = r'C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\venv\Scripts\python.exe'
powershell = ('$env:HETEROES_GPU_ACCEPTANCE="1"; $ProgressPreference="SilentlyContinue"; & \'' + python + '\' -I -B -c "' + pycode + '" --gpu --source-sha ' + sha + '; exit $LASTEXITCODE')
encoded = base64.b64encode(powershell.encode('utf-16-le')).decode()
with (OUT / 'native-launch-01.log').open('x') as log:
    result = subprocess.run(SSH + ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encoded], stdout=log, stderr=subprocess.STDOUT)
print('Native exit', result.returncode, flush=True)
with (OUT / 'native-receipts-01.tar.gz').open('xb') as target:
    subprocess.run(SSH + [f'cd {shlex.quote(WIN)} && tar -czf - codex-combined-native-run-01.json codex-combined-01'], stdout=target, check=True)
with tarfile.open(OUT / 'native-receipts-01.tar.gz') as source:
    source.extractall(OUT / '3060-native-01', filter='data')
raise SystemExit(result.returncode)
