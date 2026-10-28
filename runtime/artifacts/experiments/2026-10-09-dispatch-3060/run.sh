#!/usr/bin/env bash
# Greedy (T2) against tail-aware (U2) with the 5070 Ti and the FIRST 3060 (home wifi, Tailscale), N = 24, 3 generations, workload cot_l1_q128, chunk 64, CUDA engine, replay always.
# Same experiment id as ../2026-10-09-three-machines, so every run must end with weights a02a640b... Question: does the tail rule (the 3060 waits for the last candidate when the 5070 Ti is more than 2 times faster) shorten a generation?
# First launched with 3 repeats beside a profile of the second 3060; stopped after a few minutes (the owner asked to cut the long tests) and relaunched with 2 repeats alone.
set -uo pipefail
D=artifacts/experiments/2026-10-09-dispatch-3060
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench --repeats 2 --conditions T2,U2 \
 --candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY \
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --profile-third artifacts/experiments/2026-10-08-third-machine-3060/profile-3060-l1q128-cuda.json \
 --bind-host 0.0.0.0 --third worker-user-a@100.64.0.1 --third-url http://100.110.165.40:8765 --third-env LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811 \
 --third-replay always
