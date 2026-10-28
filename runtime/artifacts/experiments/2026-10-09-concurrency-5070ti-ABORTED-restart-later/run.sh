#!/usr/bin/env bash
# How many candidates at the same time on ONE GPU (the 5070 Ti)? B0 = 1 worker process, B0x2 = 2 processes, B0x3 = 3 processes share the GPU.
# (the two profile files are required by the script; only the 5070 Ti works here, nobody else is started.)
# Same experiment id, N = 24, 3 generations, workload cot_l1_q128, chunk 64, CUDA noise engine as ../2026-10-09-three-machines: the final weights must equal those of its B0 runs.
set -uo pipefail
D=artifacts/experiments/2026-10-09-concurrency-5070ti
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench --repeats 2 --conditions B0,B0x2,B0x3 \
 --candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY \
 --profile-reference artifacts/experiments/2026-10-08-c1-v2/profile-5070ti-l1q128-cuda.json --profile-candidate artifacts/experiments/2026-10-08-c1-v2/profile-1660s-l1q128-cuda.json
