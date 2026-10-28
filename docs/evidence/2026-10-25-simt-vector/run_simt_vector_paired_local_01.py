import os
from pathlib import Path
import shutil
import subprocess
import sys
base = Path('docs/evidence/2026-10-25-simt-vector')
probe = Path('.scratch/strict-integer-20261025/bench_simt_vector_paired_01.py')
shutil.copyfile(probe, base / 'bench-paired-01.py')
for model in ('smol', 'tiny', 'qwen'):
    out = base / f'paired-{model}-nhan-01.json'
    assert not out.exists()
    command = ['/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python', str(probe), '--gpu',
               '--model-path', f'.scratch/strict-integer-20261025/models/{model}',
               '--candidate-source', str(base / 'candidate-integer-cuda-01.py'), '--out', str(out)]
    result = subprocess.run(command, env=dict(os.environ, HETEROES_GPU_ACCEPTANCE='1', PYTHONPATH='runtime/src'))
    if result.returncode:
        sys.exit(result.returncode)
