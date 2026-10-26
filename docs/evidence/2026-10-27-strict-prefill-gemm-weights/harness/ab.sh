#!/bin/bash
# ABAB: base (HEAD archive) vs working tree, Qwen short32+chat128, separate processes.
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
export HETEROES_GPU_ACCEPTANCE=1
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
OUT=${OUT:-.scratch/claude-20261026-night/ab}; mkdir -p $OUT; rm -f $OUT/*.json
H=docs/evidence/2026-10-26-strict-prefill-attention/harness/bench_single.py
for r in a b; do for v in base new; do
  src=runtime/src; [ $v = base ] && src=.scratch/claude-20261026-night/base/runtime/src
  PYTHONPATH=$src $PY $H --gpu --model ${MODEL:-qwen} --label $v --out $OUT/$v-$r.json 2>&1 | grep -v -E "Warning|Loading"
done; done
