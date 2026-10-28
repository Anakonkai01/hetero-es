#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
while kill -0 3228943 2>/dev/null || kill -0 3210506 2>/dev/null; do sleep 3; done
export HETEROES_GPU_ACCEPTANCE=1
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=docs/evidence/2026-10-27-strict-bounded-lm-head/raw
(cd runtime && PYTHONPATH=src "$PY" -m pytest -q tests/eval/test_integer_lm_head.py > ../"$OUT"/tests-5070ti-01.log 2>&1)
PYTHONPATH=runtime/src "$PY" docs/evidence/2026-10-26-strict-prefill-attention/harness/bench_single.py --gpu --model qwen --label bounded --out "$OUT"/single-qwen-new-5070ti-pilot-01.json > "$OUT"/single-qwen-new-5070ti-pilot-01.log 2>&1
PYTHONPATH=runtime/src "$PY" docs/evidence/2026-10-27-strict-prefill-gemm-weights/harness/step_trace.py --gpu --tokens 32 --out "$OUT"/step-5070ti-pilot-01.json > "$OUT"/step-5070ti-pilot-01.log 2>&1
