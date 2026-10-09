#!/usr/bin/env bash
# Qwen3-0.6B FP32 again: the two earlier attempts ran out of memory (its cache is about 9 times bigger than Qwen2.5's, and the script kept a second copy of the weights on the GPU; now on the CPU). Chunks 16 and 32.
cd ~/projects/hetero-es
D=artifacts/experiments/2026-10-09-compact-decode
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
Q3=$(ls -d /home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/snapshots/*)
for TASK in gsm8k countdown; do
  PYTHONPATH=src $PY $D/compact_general.py --model-path $Q3 --task $TASK --gsm8k-file /tmp/claude-1000/-home-pc5070ti-projects/85a09e32-9f21-484f-ac84-8aaf67029bd1/scratchpad/data/gsm8k-test.jsonl --count 128 --max-new-tokens 512 --chunks 16,32 --candidates 2 --dtype float32 --out $D/general/qwen3-06b-$TASK-float32-chunks16-32.json 2>&1 | grep -v "Loading\|Warning\|warn\|right-padding" > $D/general/qwen3-06b-$TASK-float32-chunks16-32.log
done
echo done > $D/general/qwen3small.done
