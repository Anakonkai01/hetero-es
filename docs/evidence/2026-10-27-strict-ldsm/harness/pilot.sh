#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
while kill -0 3653843 2>/dev/null; do sleep 3; done
export HETEROES_GPU_ACCEPTANCE=1
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=docs/evidence/2026-10-27-strict-ldsm/raw
for v in base new; do
  src=.scratch/codex-20261027-bound/stage/new/src
  [ "$v" = base ] || src=.scratch/codex-20261027-ldsm/src
  "$PY" docs/evidence/2026-10-27-strict-prefill-gemm-weights/harness/gemm_bench.py --gpu --src "$src" > "$OUT/operators-$v-01.log" 2>&1
done
for r in a b; do
  for v in base new; do
    src=.scratch/codex-20261027-bound/stage/new/src
    [ "$v" = base ] || src=.scratch/codex-20261027-ldsm/src
    PYTHONPATH="$src" "$PY" docs/evidence/2026-10-26-strict-prefill-attention/harness/bench_single.py --gpu --model qwen --label "$v" --out "$OUT/single-qwen-$v-5070ti-01$r.json" > "$OUT/single-qwen-$v-5070ti-01$r.log" 2>&1
  done
done
