set -e
cd /tmp/heteroes-claude-attention-20261026-02
export HETEROES_GPU_ACCEPTANCE=1 LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib
PY=/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12
DEPS=/tmp/heteroes-strict-integer-20261025-02/testdeps
MODELS=/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models
PYTHONPATH=src:$DEPS $PY -m pytest -q -p no:cacheprovider tests/eval/test_strict_attention_split.py tests/eval/test_strict_attention_chunks.py tests/eval/test_strict_packed.py tests/eval/test_strict_cuda.py tests/eval/test_strict_decode_graph.py tests/eval/test_integer_decoder.py > tests-3060-02.log 2>&1 || echo TESTS_FAILED >> tests-3060-02.log
tail -2 tests-3060-02.log
for m in qwen smol tiny; do
  W=""; [ $m = qwen ] && W="--chat-workload workload-chat-01.json"
  PYTHONPATH=src:. $PY probe_attention_parity.py --gpu --model-name $m --model-path $MODELS/$m $W --out $m-parity-3060-02.json > $m-parity-3060-02.log 2>&1 || true
  tail -1 $m-parity-3060-02.log
done
for m in qwen smol tiny; do
  PYTHONPATH=src:. $PY bench_gqa.py --gpu --model $m --models-root $MODELS --benchmark benchmark_inference.py --probe probe_strict_backend.py --workload workload-chat-01.json --strict-cuda src/heteroes/eval/strict_cuda.py --out bench-gqa-$m-3060-02.json > bench-gqa-$m-3060-02.log 2>&1 || true
  grep -v -E 'Warning|Loading' bench-gqa-$m-3060-02.log | tail -3
done
