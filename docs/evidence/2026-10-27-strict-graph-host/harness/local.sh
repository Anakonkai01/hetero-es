#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
export HETEROES_GPU_ACCEPTANCE=1
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=$(realpath docs/evidence/2026-10-27-strict-graph-host/raw)
(cd .scratch/codex-20261027-host/new && PYTHONPATH=src "$PY" -m pytest -q tests/eval/test_strict_graph_host.py tests/eval/test_strict_decode_graph.py tests/eval/test_strict_decode_pipeline.py tests/eval/test_integer_decoder.py tests/eval/test_integer_lm_head.py::test_wide_graph_reuses_capture_matches_full_path_and_penalty_falls_back > "$OUT/gpu-5070ti-01.log" 2>&1)
for r in a b; do
  for v in base new; do
    src=.scratch/codex-20261027-bound/stage/new/src
    [ "$v" = base ] || src=.scratch/codex-20261027-host/new/src
    PYTHONPATH="$src" "$PY" docs/evidence/2026-10-26-strict-prefill-attention/harness/bench_single.py --gpu --model qwen --label "$v" --out "$OUT/single-qwen-$v-5070ti-01$r.json" > "$OUT/single-qwen-$v-5070ti-01$r.log" 2>&1
  done
done
