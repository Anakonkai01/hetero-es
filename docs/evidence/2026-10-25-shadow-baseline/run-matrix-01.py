"""Reproduce the remaining local matrix sequentially; each process owns its GPU models.

The initial qwen-hf-shadow-full-01 job was launched separately with the same common arguments.
An existing destination is rejected, never silently skipped or overwritten.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
PYTHON = Path('/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python')
MODELS = Path('/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models')

jobs = []
for model in ('qwen', 'smol', 'tiny'):
    if model != 'qwen':
        jobs.append((model, 'hf-shadow-full', 'hf-shadow', []))
    jobs.append((model, 'b22', 'strict-integer', []))
    config = json.loads((MODELS / model / 'config.json').read_text())
    head = bool(config.get('tie_word_embeddings', False))
    jobs.append((model, 'frozen-head' if head else 'frozen-no-head', 'strict-frozen', ['--frozen-head'] if head else []))
    jobs.append((model, 'hf-shadow-chunk16', 'hf-shadow', ['--hf-chunk', '16', '--batch-sizes', '32']))

for model, label, engine, extra in jobs:
    destination = EVIDENCE / 'raw' / f'{model}-{label}-01.json'
    log = destination.with_suffix('.log')
    command = [str(PYTHON), 'runtime/scripts/benchmark_inference.py', '--gpu', '--engine', engine,
               '--model-path', str(MODELS / model), '--repeats', '5', '--graph-max-bytes', str(4 * 1024**3),
               '--out', str(destination), *extra]
    if destination.exists() or log.exists():
        raise FileExistsError(destination)
    print(f'START {model} {label}', flush=True)
    with log.open('x') as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                env={**os.environ, 'HETEROES_GPU_ACCEPTANCE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                                     'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'PYTHONPATH': 'runtime/src'})
    if result.returncode:
        print(f'FAILED {destination}; exit={result.returncode}', flush=True)
        sys.exit(result.returncode)
    data = json.loads(destination.read_text())
    if data['status'] != 'ok':
        raise RuntimeError(data)
    print('DONE ' + model + ' ' + label + ' ' + json.dumps([
        {'batch': c['sequences'], 'tokensPerSecond': round(c['tokensPerSecondTotal'], 1)} for c in data['cases']
    ]), flush=True)

print('ALL JOBS TERMINAL', flush=True)
