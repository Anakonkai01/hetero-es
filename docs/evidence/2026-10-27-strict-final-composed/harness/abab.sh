#!/usr/bin/env bash
# ABAB: two rounds of baseline/composed, separate processes, fresh outputs.
set -euo pipefail
cd "$(dirname "$0")/../../../.."
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=docs/evidence/2026-10-27-strict-final-composed/raw
H=docs/evidence/2026-10-27-strict-final-composed/harness/bench_composed.py
for round in 1 2; do
  for v in baseline composed; do
    HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src "$PY" "$H" --gpu --variant "$v" --out "$OUT/$v-r$round.json" 2>&1 | tee "$OUT/$v-r$round.log"
  done
done
echo ABAB-DONE
