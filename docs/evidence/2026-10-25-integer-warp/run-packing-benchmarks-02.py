import os,subprocess,sys
from pathlib import Path
base=Path('docs/evidence/2026-10-25-integer-warp');python='/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python'
for kind in ('shift','prmt'):
 env=dict(os.environ,HETEROES_GPU_ACCEPTANCE='1',PYTHONPATH=f'.scratch/strict-integer-20261025/packing-plan-{kind}-02/src')
 for model in ('smol','tiny','qwen'):
  out=base/f'bench-packing-{kind}-{model}-nhan-02.json';assert not out.exists()
  cmd=[python,'runtime/scripts/benchmark_inference.py','--engine','strict-integer','--integer-bits','22','--gpu','--model-path',f'.scratch/strict-integer-20261025/models/{model}','--out',str(out),'--graph-max-bytes','4294967296']
  result=subprocess.run(cmd,env=env)
  if result.returncode:sys.exit(result.returncode)
