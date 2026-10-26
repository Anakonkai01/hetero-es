#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
export HETEROES_GPU_ACCEPTANCE=1
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
STAGE=$(realpath .scratch/codex-20261027-combined/stage)
OUT=$(realpath docs/evidence/2026-10-27-strict-combined-acceptance/raw)
H=docs/evidence/2026-10-26-strict-prefill-attention/harness
for r in a b; do
  for v in base new; do
    PYTHONPATH="$STAGE/$v/src" "$PY" "$H/bench_single.py" --gpu --model qwen --label "$v" --out "$OUT/single-qwen-$v-5070ti-01$r.json" > "$OUT/single-qwen-$v-5070ti-01$r.log" 2>&1
  done
done
for m in qwen smol tiny; do
  probe="$STAGE/probe_projection_parity.py"
  extra=()
  if [ "$m" = qwen ]; then
    probe="$H/probe_native_frozen_eos.py"
    extra=(--chat-workload docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json --eos-control "$H/eos-control-01.json")
  fi
  PYTHONPATH="$STAGE/new/src:$STAGE/new/scripts" "$PY" "$probe" --gpu --model-name "$m" --model-path "/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/$m" "${extra[@]}" --out "$OUT/$m-parity-5070ti-01.json" > "$OUT/$m-parity-5070ti-01.log" 2>&1
done
(cd "$STAGE/new" && PYTHONPATH=src "$PY" -m pytest -q -p no:cacheprovider tests/eval/test_strict_*.py tests/eval/test_integer_*.py tests/eval/test_fp16_decoder_cuda.py > "$OUT/tests-5070ti-full-01.log" 2>&1)
