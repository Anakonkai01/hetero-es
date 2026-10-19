#!/usr/bin/env bash
# The compacting decoder as a recipe option, in the real system: the 5070 Ti alone (B0), N = 24, 3 generations, workload cot_l1_q128, CUDA engine, FP32, chunk 64, experiment id c1v2,
# the same as ../2026-10-09-three-machines. hf_compact: 2 runs; hf_generate (the default engine): 1 run in the same session for a fair time. All final weights must be the same as those
# of the earlier B0 runs (a02a640b...) IF the rewards are equal, which equal texts give.
set -uo pipefail
D=artifacts/experiments/2026-10-09-decode-engine-b0
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
COMMON="--candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --conditions B0"
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench-compact --repeats 2 $COMMON --decode-engine hf_compact
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench-generate --repeats 1 $COMMON --decode-engine hf_generate
echo done > $D/done
