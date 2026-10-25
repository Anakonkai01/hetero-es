import os,subprocess,sys
from pathlib import Path
base=Path('docs/evidence/2026-10-25-integer-prepacked');python='/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python';env=dict(os.environ,HETEROES_GPU_ACCEPTANCE='1',PYTHONPATH='runtime/src')
for model in ('smol','tiny','qwen'):
 for kind in ('bench','quality'):
  out=base/f'selected-{kind}-{model}-nhan-01.json';assert not out.exists()
  cmd=[python,'runtime/scripts/benchmark_inference.py','--engine','strict-integer','--integer-bits','22','--graph-max-bytes','4294967296']if kind=='bench'else[python,'runtime/scripts/probe_integer_decoder.py']
  cmd+=['--gpu','--model-path',f'.scratch/strict-integer-20261025/models/{model}','--out',str(out)]
  r=subprocess.run(cmd,env=env)
  if r.returncode:sys.exit(r.returncode)
