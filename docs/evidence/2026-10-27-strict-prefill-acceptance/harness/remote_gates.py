"""Reproduce the requested prefill gates on the named 3060, WSL2 then native Windows.

Fresh cache paths; frozen HEAD sources and existing harnesses. No lab/device state changes.
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
OUT = REPO / 'docs/evidence/2026-10-27-strict-prefill-acceptance/raw'
SSH = ['ssh', '-F', '/home/pc5070ti/.ssh/config', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'thao_nguyen@100.92.20.58']
STAGE = '/tmp/heteroes-codex-prefill-acceptance-20261027-01'
archive = REPO / '.scratch/codex-20261027-prefill/source-01.tar.gz'
command = f'mkdir {shlex.quote(STAGE)} && tar -xzf - -C {shlex.quote(STAGE)} && cd {shlex.quote(STAGE)} && RUN=01 bash remote_3060.sh > remote-console-01.log 2>&1'
with archive.open('rb') as source, (OUT / 'wsl-launch-01.log').open('x') as log:
    result = subprocess.run(SSH + [command], stdin=source, stdout=log, stderr=subprocess.STDOUT)
print('WSL2 controller exit', result.returncode, flush=True)
# Fetch all receipts, keeping the already sealed source out of the result bundle.
fetch = f'cd {shlex.quote(STAGE)} && tar -czf - --wildcards --no-recursion *.log *.json'
with (OUT / 'wsl-receipts-01.tar.gz').open('xb') as target:
    subprocess.run(SSH + [fetch], stdout=target, check=True)
with tarfile.open(OUT / 'wsl-receipts-01.tar.gz') as source:
    source.extractall(OUT / '3060-wsl-01', filter='data')

HERE = REPO / 'docs/evidence/2026-10-26-strict-prefill-attention'
def tree(commit, paths):
    data = subprocess.run(['git', 'archive', commit, *paths], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as source:
        return {item.name.removeprefix('runtime/'): source.extractfile(item).read() for item in source.getmembers() if item.isfile()}
files = {f'new/{k}': v for k, v in tree('f3747900', ['runtime/src', 'runtime/tests', 'runtime/scripts/benchmark_inference.py', 'runtime/scripts/probe_strict_backend.py']).items()}
files.update({f'base/{k}': v for k, v in tree('a7884392', ['runtime/src']).items()})
files['new/COMMIT'] = subprocess.run(['git', 'rev-parse', 'f3747900'], capture_output=True, check=True).stdout
for name in ('probe_projection_parity.py', 'probe_native_frozen_eos.py', 'frozen_eos.py', 'eos-control-01.json', 'bench_single.py'):
    files[name] = (HERE / 'harness' / name).read_bytes()
files['workload-chat-01.json'] = (REPO / 'docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_bytes()
manifest = {'files': {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}}
files['source-manifest-01.json'] = json.dumps(manifest, indent=1).encode()
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w:gz') as source:
    for name, data in sorted(files.items()):
        item = tarfile.TarInfo(name)
        item.size, item.mtime = len(data), 0
        source.addfile(item, io.BytesIO(data))
packed = buffer.getvalue()
sha = hashlib.sha256(packed).hexdigest()
(OUT / 'native-source-02.sha256').write_text(f'{sha}  source-codex-prefill-02.tar.gz\n')
(OUT / 'native-source-manifest-02.json').write_bytes(files['source-manifest-01.json'])
path = '/mnt/c/Users/Thao Nguyen/.cache/heteroes-native-strict-20261025-01/source-codex-prefill-02.tar.gz'
subprocess.run(SSH + [f'test ! -e {shlex.quote(path)} && cat > {shlex.quote(path)} && sha256sum {shlex.quote(path)}'], input=packed, check=True)
code = (HERE / 'harness/native_windows.py').read_text().replace('codex-prefill-01', 'codex-prefill-02').replace('codex-prefill-native-run-01', 'codex-prefill-native-run-02')
code = code.replace("'test_integer_stream',", "'test_integer_weights_batched','test_integer_stream',")
(REPO / 'docs/evidence/2026-10-27-strict-prefill-acceptance/harness/native_windows_02.py').write_text(code)
pycode = "exec(__import__('base64').b64decode('" + base64.b64encode(code.encode()).decode() + "'))"
python = r'C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\venv\Scripts\python.exe'
script = ('$env:HETEROES_GPU_ACCEPTANCE="1"; $ProgressPreference="SilentlyContinue"; & \'' + python + '\' -I -B -c "' + pycode + '" --gpu --source-sha ' + sha + '; exit $LASTEXITCODE')
encoded = base64.b64encode(script.encode('utf-16-le')).decode()
with (OUT / 'native-launch-02.log').open('x') as log:
    result = subprocess.run(SSH + ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encoded], stdout=log, stderr=subprocess.STDOUT)
print('Native controller exit', result.returncode, flush=True)
root = '/mnt/c/Users/Thao Nguyen/.cache/heteroes-native-strict-20261025-01'
fetch = f'cd {shlex.quote(root)} && tar -czf - codex-prefill-native-run-02.json codex-prefill-02'
with (OUT / 'native-receipts-02.tar.gz').open('xb') as target:
    subprocess.run(SSH + [fetch], stdout=target, check=True)
with tarfile.open(OUT / 'native-receipts-02.tar.gz') as source:
    source.extractall(OUT / '3060-native-02', filter='data')
