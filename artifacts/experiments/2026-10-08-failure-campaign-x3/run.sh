#!/usr/bin/env bash
# The failure campaign of G6 (four scenarios) plus kill-coordinator-mid-update, three times, N = 8, 3 generations, FP32, chunk 16, the 16-prompt workload, as in ../2026-10-07-g6-failure-campaign.
# The sudo password for the cut-link scenario comes from the environment (HETEROES_SUDO_PASSWORD), never from a file of the repository.
set -uo pipefail
D=artifacts/experiments/2026-10-08-failure-campaign-x3
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
for REP in 1 2 3; do
  PYTHONPATH=src $PY scripts/failure_campaign.py --out-dir $D/rep$REP --candidates 8 --generations 3 --chunk 16 --eval-dtype float32 \
    --scenarios kill-worker,pause-worker,cut-link,kill-coordinator,kill-coordinator-mid-update --local-python $PY
done
