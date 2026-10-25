"""Repeat the close Tiny B32 comparison in A/B/B/A order, using separate sequential processes."""

import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PYTHON = '/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python'
MODEL = '/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/tiny'
for label, engine in (('a1', 'hf-shadow'), ('b1', 'strict-frozen'), ('b2', 'strict-frozen'), ('a2', 'hf-shadow')):
    destination = HERE / 'raw' / f'tiny-b32-abba-{label}-01.json'
    log = destination.with_suffix('.log')
    if destination.exists() or log.exists():
        raise FileExistsError(destination)
    command = [PYTHON, 'runtime/scripts/benchmark_inference.py', '--gpu', '--engine', engine,
               '--model-path', MODEL, '--batch-sizes', '32', '--repeats', '5',
               '--graph-max-bytes', str(4 * 1024**3), '--out', str(destination)]
    print(f'START {label} {engine}', flush=True)
    with log.open('x') as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True,
                       env={**os.environ, 'HETEROES_GPU_ACCEPTANCE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'PYTHONPATH': 'runtime/src'})
    data = json.loads(destination.read_text())
    assert data['status'] == 'ok'
    print(f"DONE {label} {data['cases'][0]['tokensPerSecondTotal']:.1f} tok/s", flush=True)
print('ALL JOBS TERMINAL', flush=True)
