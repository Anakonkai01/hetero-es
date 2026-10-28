"""Build a manifest-checked archive (new = HEAD, base = 48547ba3), copy it to Thao's Windows cache and run the native harness."""
import base64, hashlib, io, json, subprocess, tarfile
from pathlib import Path
here = Path('docs/evidence/2026-10-26-strict-prefill-attention')
ssh = ['ssh', '-F', '/home/pc5070ti/.ssh/config', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'thao_nguyen@100.92.20.58']
def tree(commit, paths):
    data = subprocess.run(['git', 'archive', commit, *paths], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        return {m.name.removeprefix('runtime/'): t.extractfile(m).read() for m in t.getmembers() if m.isfile()}
files = {f'new/{k}': v for k, v in tree('HEAD', ['runtime/src', 'runtime/tests', 'runtime/scripts/benchmark_inference.py',
                                                 'runtime/scripts/probe_strict_backend.py']).items()}
files.update({f'base/{k}': v for k, v in tree('48547ba3', ['runtime/src']).items()})
files['new/COMMIT'] = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, check=True).stdout
for name in ('probe_projection_parity.py', 'probe_native_frozen_eos.py', 'frozen_eos.py', 'eos-control-01.json', 'bench_single.py'):
    files[name] = (here / 'harness' / name).read_bytes()
files['workload-chat-01.json'] = Path('docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json').read_bytes()
manifest = {'files': {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}}
files['source-manifest-01.json'] = json.dumps(manifest, indent=1).encode()
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w:gz') as t:
    for name, data in sorted(files.items()):
        info = tarfile.TarInfo(name); info.size = len(data); info.mtime = 0; t.addfile(info, io.BytesIO(data))
archive = buffer.getvalue(); sha = hashlib.sha256(archive).hexdigest()
(here / 'raw/3060-native-01').mkdir(parents=True, exist_ok=True)
(here / 'raw/3060-native-01/source-manifest-01.json').write_bytes(files['source-manifest-01.json'])
(here / 'raw/3060-native-01/source-01.sha256').write_text(f'{sha}  source-codex-prefill-01.tar.gz\n')
target = '/mnt/c/Users/Thao Nguyen/.cache/heteroes-native-strict-20261025-01/source-codex-prefill-01.tar.gz'
subprocess.run(ssh + [f'test ! -e "{target}" && cat > "{target}" && sha256sum "{target}"'], input=archive, check=True)
code = (here / 'harness/native_windows.py').read_bytes()
pycode = "exec(__import__('base64').b64decode('" + base64.b64encode(code).decode() + "'))"
python = r'C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\venv\Scripts\python.exe'
script = ('$env:HETEROES_GPU_ACCEPTANCE="1"; $ProgressPreference="SilentlyContinue"; & \'' + python + '\' -I -B -c "' + pycode +
          '" --gpu --source-sha ' + sha + '; exit $LASTEXITCODE')
encoded = base64.b64encode(script.encode('utf-16-le')).decode()
subprocess.run(ssh + ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encoded], check=True)
