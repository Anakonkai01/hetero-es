#!/usr/bin/env bash
# The G7 cluster benchmark: the long workload (cot_l3_q32), N = 24, 4 generations, FP32, chunk 16, B0x2 / B3x2 / B4x2, once with the CPU noise engine and once with the CUDA one.
# Usage: bash run_campaign.sh REPEATS     (from the repository root; both machines on the same commit; the 5070 Ti side in the heteroes-match environment)
set -euo pipefail
REPEATS=${1:-3}
D=artifacts/experiments/2026-10-07-g7-cluster-benchmark
PY=~/miniforge3/envs/heteroes-match/bin/python
for ENGINE in cpu cuda; do
  PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/$ENGINE-engine --candidates 24 --generations 4 --repeats "$REPEATS" \
    --conditions B0x2,B3x2,B4x2 --profile-reference $D/profiles-derived/profile-5070ti-$ENGINE-engine.json \
    --profile-candidate $D/profiles-derived/profile-1660s-$ENGINE-engine.json --chunk 16 --eval-dtype float32 \
    --noise-engine $ENGINE --workload cot_l3_q32 --coordinator-noise-threads 28 --experiment-id g7bench --run-timeout 3000
done
