#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
export HETEROES_GPU_ACCEPTANCE=1
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=docs/evidence/2026-10-27-strict-balanced-decode/raw
for r in a b; do
  for v in base new; do
    src=.scratch/codex-20261027-bound/stage/new/src
    [ "$v" = base ] || src=.scratch/codex-20261027-balanced/src
    PYTHONPATH="$src" "$PY" docs/evidence/2026-10-26-strict-prefill-attention/harness/bench_single.py --gpu --model qwen --label "$v" --out "$OUT/single-qwen-$v-5070ti-01$r.json" > "$OUT/single-qwen-$v-5070ti-01$r.log" 2>&1
  done
done
