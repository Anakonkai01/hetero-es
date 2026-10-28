#!/bin/bash
# 3060 WSL2: strict/integer GPU suites, trained parity (tile vs stream, parent/±/restore, Qwen chat + EOS),
# then ABAB whole-generation timing of base (75f92c30) vs new. Run inside the extracted stage directory.
set -u
export HETEROES_GPU_ACCEPTANCE=1 LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib
PY=/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12
DEPS=/tmp/heteroes-strict-integer-20261025-02/testdeps
MODELS=/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models
sha256sum -c --quiet SHA256SUMS > stage-check.log 2>&1 && echo STAGE_OK >> stage-check.log || echo STAGE_FAILED >> stage-check.log
(cd new && PYTHONPATH=src:$DEPS $PY -m pytest -q -p no:cacheprovider tests/eval/test_strict_*.py tests/eval/test_integer_*.py \
  > ../tests-3060-01.log 2>&1 || echo TESTS_FAILED >> ../tests-3060-01.log)
tail -2 tests-3060-01.log
for m in qwen smol tiny; do
  W=""; [ $m = qwen ] && W="--chat-workload workload-chat-01.json"
  PYTHONPATH=new/src:new/scripts $PY probe_projection_parity.py --gpu --model-name $m --model-path $MODELS/$m $W \
    --out $m-parity-3060-01.json > $m-parity-3060-01.log 2>&1 || true
  tail -1 $m-parity-3060-01.log
done
for m in qwen smol tiny; do
  for r in 01 02; do
    for v in base new; do
      PYTHONPATH=$v/src $PY bench_single.py --gpu --model $m --models-root $MODELS --benchmark new/scripts/benchmark_inference.py \
        --probe new/scripts/probe_strict_backend.py --workload workload-chat-01.json --label $v \
        --out single-$m-$v-3060-$r.json > single-$m-$v-3060-$r.log 2>&1 || echo BENCH_FAILED >> single-$m-$v-3060-$r.log
      grep -v -E 'Warning|Loading' single-$m-$v-3060-$r.log | tail -2
    done
  done
done
echo REMOTE_DONE
