import os
from pathlib import Path
import subprocess
import sys
base = Path('docs/evidence/2026-10-25-mma-vector')
python = '/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python'
with (base / 'operator-nhan-01.log').open('x') as log:
    result = subprocess.run([python, '-m', 'pytest', 'runtime/tests/eval/test_integer_cuda.py', '-q'],
                            env=dict(os.environ, HETEROES_GPU_ACCEPTANCE='1', PYTHONPATH='.scratch/strict-integer-20261025/mma-vector-01/src'),
                            stdout=log, stderr=subprocess.STDOUT)
if result.returncode:
    sys.exit(result.returncode)
for model in ('smol', 'tiny', 'qwen'):
    out = base / f'paired-{model}-nhan-01.json'
    assert not out.exists()
    result = subprocess.run([python, '.scratch/strict-integer-20261025/bench_simt_vector_paired_01.py', '--gpu',
                             '--model-path', f'.scratch/strict-integer-20261025/models/{model}',
                             '--candidate-source', str(base / 'candidate-integer-cuda-01.py'), '--out', str(out)],
                            env=dict(os.environ, HETEROES_GPU_ACCEPTANCE='1', PYTHONPATH='runtime/src'))
    if result.returncode:
        sys.exit(result.returncode)
