#!/usr/bin/env bash
# G7, bigger chunk: the cluster benchmark with the CUDA noise engine and a bigger number of prompts per generate() call.
#   cot_l3_q32 @ chunk 32 : the same workload as the first G7 benchmark (speed only)       cot_l3_q64 @ chunk 64 : twice the questions per candidate (less noisy rewards)
# Usage: bash run_campaign.sh REPEATS    (from the repository root; both machines on the same commit; the 5070 Ti side in the heteroes-match environment)
set -euo pipefail
REPEATS=${1:-3}
D=artifacts/experiments/2026-10-07-g7-bigchunk
PY=~/miniforge3/envs/heteroes-match/bin/python
for CFG in "cot_l3_q32 32 B0x2,B3x2,B4x2" "cot_l3_q64 64 B0x2,B3x2,B4x2,B0"; do
  set -- $CFG
  PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/$1-chunk$2 --candidates 24 --generations 4 --repeats "$REPEATS" --conditions $3 \
    --profile-reference $D/profiles-derived/profile-5070ti-$1.json --profile-candidate $D/profiles-derived/profile-1660s-$1.json --chunk $2 --eval-dtype float32 \
    --noise-engine cuda --workload $1 --coordinator-noise-threads 28 --experiment-id g7big --run-timeout 3000
done
