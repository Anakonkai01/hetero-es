#!/usr/bin/env bash
# How much faster do K candidates run at the SAME time on ONE GPU than one after the other? Run this ON the machine whose GPU is measured.
#   bash run_probe.sh <out dir> <python> <model snapshot dir> [K list, default "1 2 3"] [chunk, default 64]
# (put PYTHONPATH=src and, on a WSL2 box, LD_LIBRARY_PATH in the environment first; run it from the repo root.)
# For each K it starts K copies of scripts/chunk_text_record.py at the same moment (each: the parent + 4 perturbed candidates, answers at the chunk, seconds per condition).
# Output: <out>/k<K>-p<i>.json, <out>/k<K>-wall.txt (wall seconds of the whole group). Evidence is never overwritten (the out dir must not exist).
set -uo pipefail
OUT=$1; PY=$2; MODEL=$3; KS=${4:-"1 2 3"}; CHUNK=${5:-64}
[ -e "$OUT" ] && { echo "$OUT exists" >&2; exit 2; }
mkdir -p "$OUT"
for K in $KS; do
  start=$(date +%s.%N)
  for i in $(seq 1 "$K"); do
    $PY scripts/chunk_text_record.py run --model-path "$MODEL" --workload cot_l1_q128 --noise-engine cuda --chunk "$CHUNK" --candidates 4 --out "$OUT/k$K-p$i.json" > "$OUT/k$K-p$i.log" 2>&1 &
  done
  wait
  end=$(date +%s.%N)
  echo "$K $(awk "BEGIN{print $end - $start}")" > "$OUT/k$K-wall.txt"
done
