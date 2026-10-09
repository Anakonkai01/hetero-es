#!/usr/bin/env bash
# N = 48 and N = 96 with the 5070 Ti and the borrowed 3060 (the 1660S was down): B0 (5070 Ti alone) against T2 (+ 3060 by replay), as in ../2026-10-09-three-machines (same
# workload, chunk 64, CUDA engine, FP32, experiment id c1v2 so that B0 and T2 of the same N must end with the same weights). The predictions were written first (prediction-n48.json, prediction-n96.json).
set -uo pipefail
cd ~/projects/hetero-es
D=artifacts/experiments/2026-10-09-scaling-n48-n96-2machines
C=artifacts/experiments/2026-10-08-c1-v2
M=artifacts/experiments/2026-10-08-third-machine-3060
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
COMMON="--generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 6000 --local-python $PY
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --profile-third $M/profile-3060-l1q128-cuda.json
 --bind-host 0.0.0.0 --third thao_nguyen@100.92.20.58 --third-url http://100.110.165.40:8765 --third-env LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811
 --third-replay auto --third-replay-profile /tmp/profile-3060-with-sync.json"
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/n48 --candidates 48 --repeats 2 --conditions B0,T2 $COMMON
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/n96 --candidates 96 --repeats 1 --conditions B0,T2 $COMMON
