#!/bin/bash
# 5070 Ti: the same stage archive as the 3060 run. Trained parity at HEAD, then ABAB base (BASE) vs new.
# Usage: local_5070ti_01.sh <extracted stage dir> <output dir>
set -u
RUN=${RUN:-01}
stage=$(realpath $1); out=$(realpath $2)
export HETEROES_GPU_ACCEPTANCE=1
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
MODELS=/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models
cd $stage
for m in qwen smol tiny; do
  W=""; [ $m = qwen ] && W="--chat-workload workload-chat-01.json"
  PYTHONPATH=new/src:new/scripts $PY probe_projection_parity.py --gpu --model-name $m --model-path $MODELS/$m $W \
    --out $out/$m-parity-5070ti-${RUN}.json > $out/$m-parity-5070ti-${RUN}.log 2>&1 || true
  tail -1 $out/$m-parity-5070ti-${RUN}.log
done
for m in qwen smol tiny; do
  for r in a b; do
    for v in base new; do
      PYTHONPATH=$v/src $PY bench_single.py --gpu --model $m --models-root $MODELS --benchmark new/scripts/benchmark_inference.py \
        --probe new/scripts/probe_strict_backend.py --workload workload-chat-01.json --label $v \
        --out $out/single-$m-$v-5070ti-${RUN}$r.json > $out/single-$m-$v-5070ti-${RUN}$r.log 2>&1 || echo BENCH_FAILED >> $out/single-$m-$v-5070ti-${RUN}$r.log
      grep -v -E 'Warning|Loading' $out/single-$m-$v-5070ti-${RUN}$r.log | tail -2
    done
  done
done
echo LOCAL_DONE
