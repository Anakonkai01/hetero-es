#!/usr/bin/env bash
# kill-worker and pause-worker again, three times, on the LONG workload (cot_l1_q128, CUDA engine, chunk 64): a candidate takes about 7 s on the 5070 Ti and 28 s on the 1660S, so the
# 1660S always holds a candidate when the scenario waits for it (with the 16 prompts of ../2026-10-08-failure-campaign-x3 the 5070 Ti sometimes finished everything before the 1660S was ready).
set -uo pipefail
D=artifacts/experiments/2026-10-08-failure-campaign-long-workers
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
for REP in 1 2 3; do
  PYTHONPATH=src $PY scripts/failure_campaign.py --out-dir $D/rep$REP --candidates 8 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 \
    --scenarios kill-worker,pause-worker --coordinator-noise-threads 28 --lease-seconds 60 --run-timeout 1800 --local-python $PY
done
