#!/usr/bin/env bash
# follow-up of the matrix (09/10): (1) batch-shape sensitivity of the TEXT (library 64 against library 128, no compaction), Qwen2.5-0.5B, GSM8K and countdown, FP32;
# (2) Qwen3-0.6B again, which ran out of memory at chunk 128 (8 KV heads x 128: a bigger cache), with chunks 32 and 64; bf16 with chunk 64.
cd ~/projects/hetero-es
D=artifacts/experiments/2026-10-09-compact-decode
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
Q25=$(ls -d /home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/*)
Q3=$(ls -d /home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/snapshots/*)
for TASK in gsm8k countdown; do
  PYTHONPATH=src $PY $D/batch_shape_sensitivity.py --model-path $Q25 --task $TASK --gsm8k-file /tmp/claude-1000/-home-pc5070ti-projects/85a09e32-9f21-484f-ac84-8aaf67029bd1/scratchpad/data/gsm8k-test.jsonl --out $D/general/sensitivity-qwen25-$TASK.json 2>&1 | grep -v "Loading\|Warning\|warn\|right-padding" > $D/general/sensitivity-qwen25-$TASK.log
done
for TASK in gsm8k countdown; do
  PYTHONPATH=src $PY $D/compact_general.py --model-path $Q3 --task $TASK --gsm8k-file /tmp/claude-1000/-home-pc5070ti-projects/85a09e32-9f21-484f-ac84-8aaf67029bd1/scratchpad/data/gsm8k-test.jsonl --count 128 --max-new-tokens 512 --chunks 32,64 --candidates 2 --dtype float32 --out $D/general/qwen3-06b-$TASK-float32-chunks32-64.json 2>&1 | grep -v "Loading\|Warning\|warn\|right-padding" > $D/general/qwen3-06b-$TASK-float32-chunks32-64.log
done
PYTHONPATH=src $PY $D/compact_general.py --model-path $Q3 --task gsm8k --gsm8k-file /tmp/claude-1000/-home-pc5070ti-projects/85a09e32-9f21-484f-ac84-8aaf67029bd1/scratchpad/data/gsm8k-test.jsonl --count 128 --max-new-tokens 512 --chunks 64 --candidates 2 --dtype bfloat16 --out $D/general/qwen3-06b-gsm8k-bfloat16-chunk64.json 2>&1 | grep -v "Loading\|Warning\|warn\|right-padding" > $D/general/qwen3-06b-gsm8k-bfloat16-chunk64.log
echo done > $D/general/followup.done
