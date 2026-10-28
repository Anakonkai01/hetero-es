#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
export HETEROES_GPU_ACCEPTANCE=1
export PYTHONPATH=/home/pc5070ti/projects/heteroes-codex-frozen-perf/.scratch/codex-20261027-combined/stage/new/src
NCU=/home/pc5070ti/projects/heteroes-codex-frozen-perf/.scratch/codex-20261027-ncu/nsight_compute-linux-x86_64-2026.1.1.2-archive/ncu
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=docs/evidence/2026-10-27-strict-counter-profile/raw
for c in prefill-down decode-gate decode-down bound-head attention; do
 "$NCU" --set full --clock-control none --cache-control all --profile-from-start off --kernel-name 'regex:(integer_stream|integer_stream_group|bound_scores|strict_attention_gqa)$' --launch-count 1 --export "$OUT/$c-01" "$PY" docs/evidence/2026-10-27-strict-counter-profile/harness/profile_kernel_v2.py --gpu --case "$c" --out "$OUT/$c-01.json" > "$OUT/$c-01.log" 2>&1
 "$NCU" --import "$OUT/$c-01.ncu-rep" --page details > "$OUT/$c-01.txt"
 "$NCU" --import "$OUT/$c-01.ncu-rep" --page raw --csv > "$OUT/$c-01.csv"
 echo "Finished $c"
done
