"""Copy the source archive to Thao's Windows cache and run the native harness through PowerShell (same GPU as WSL2)."""
import base64, hashlib, subprocess
from pathlib import Path
root = Path('.scratch/claude-attention-split-20261026')
ssh = ['ssh', '-F', '/home/pc5070ti/.ssh/config', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'thao_nguyen@100.92.20.58']
archive = root / 'native-source-01.tar.gz'
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
target = '/mnt/c/Users/Thao Nguyen/.cache/heteroes-native-strict-20261025-01/source-claude-attention-01.tar.gz'
subprocess.run(ssh + [f'test ! -e "{target}" && cat > "{target}" && sha256sum "{target}"'], input=archive.read_bytes(), check=True)
code = (root / 'harness/native_windows_attention_01.py').read_bytes()
pycode = "exec(__import__('base64').b64decode('" + base64.b64encode(code).decode() + "'))"
python = r'C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\venv\Scripts\python.exe'
script = ('$env:HETEROES_GPU_ACCEPTANCE="1"; $ProgressPreference="SilentlyContinue"; & \'' + python + '\' -I -B -c "' + pycode +
          '" --gpu --source-sha ' + sha + '; exit $LASTEXITCODE')
encoded = base64.b64encode(script.encode('utf-16-le')).decode()
subprocess.run(ssh + ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encoded], check=True)
