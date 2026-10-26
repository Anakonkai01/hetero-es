"""Repair the obsolete test dependency path, rerun frozen WSL source tests before native uses the GPU."""
import os
from pathlib import Path
import signal
import subprocess

controller = 3028458
ssh = ['ssh', '-F', '/home/pc5070ti/.ssh/config', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'thao_nguyen@100.92.20.58']
command = '''while pgrep -f '^bash remote_3060.sh$' >/dev/null; do sleep 5; done
cd /tmp/heteroes-codex-prefill-acceptance-20261027-01/new
export HETEROES_GPU_ACCEPTANCE=1
export LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib
export PYTHONPATH=src:/tmp/heteroes-codex-prefill-20261026-02/testdeps
test ! -e ../tests-3060-02.log || exit 2
/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12 -m pytest -q -p no:cacheprovider tests/eval/test_strict_*.py tests/eval/test_integer_*.py tests/eval/test_fp16_decoder_cuda.py > ../tests-3060-02.log 2>&1
status=$?
tail -4 ../tests-3060-02.log
exit "$status"
'''
os.kill(controller, signal.SIGSTOP)
try:
    with Path('docs/evidence/2026-10-27-strict-prefill-acceptance/raw/wsl-tests-retry-02.log').open('x') as log:
        result = subprocess.run(ssh + [command], stdout=log, stderr=subprocess.STDOUT)
    print('Frozen WSL retry exit', result.returncode, flush=True)
finally:
    os.kill(controller, signal.SIGCONT)
