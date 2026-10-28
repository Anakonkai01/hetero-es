#!/usr/bin/env bash
# Replay in the worker, two machines: the same experiment as B3 of ../2026-10-08-c1-v2 (experiment id c1v2, so the seeds, and therefore the final weights,
# must be those of that folder), with the 1660S catching up by download (never), by replaying the update records (always), or by the rule of its profile (auto).
set -uo pipefail
D=artifacts/experiments/2026-10-08-replay-worker
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
COMMON="--candidates 24 --generations 3 --conditions B3 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY"
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/never  --repeats 2 $COMMON --replay never
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/always --repeats 2 $COMMON --replay always
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/auto   --repeats 1 $COMMON --replay auto --replay-profile /tmp/c1v2/profile-1660s-l1q128-cuda.json
