#!/usr/bin/env bash
# models x tasks on the 5070 Ti, FP32, 128 questions, 512 new tokens at most, parent + 2 noisy candidates, chunks 64 and 128. GSM8K test file: /tmp/claude-1000/-home-pc5070ti-projects/85a09e32-9f21-484f-ac84-8aaf67029bd1/scratchpad/data/gsm8k-test.jsonl (downloaded from github.com/openai/grade-school-math, not kept in the repo).
set -uo pipefail
cd ~/projects/hetero-es
D=artifacts/experiments/2026-10-09-compact-decode/general
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
Q25=$(ls -d /home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/*)
Q3=$(ls -d /home/pc5070ti/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/snapshots/*)
SM=$(ls -d /home/pc5070ti/.cache/huggingface/hub/models--HuggingFaceTB--SmolLM2-360M-Instruct/snapshots/*)
run() { # name path task dtype
  PYTHONPATH=src $PY artifacts/experiments/2026-10-09-compact-decode/compact_general.py --model-path $2 --task $3 --gsm8k-file /tmp/claude-1000/-home-pc5070ti-projects/85a09e32-9f21-484f-ac84-8aaf67029bd1/scratchpad/data/gsm8k-test.jsonl --count 128 --max-new-tokens 512 --chunks 64,128 --candidates 2 --dtype $4 --out $D/$1-$3-$4.json 2>&1 | grep -v "Loading\|Warning\|warn\|right-padding" > $D/$1-$3-$4.log
}
for TASK in gsm8k countdown sudoku4; do
  run qwen25-05b $Q25 $TASK float32
  run qwen3-06b $Q3 $TASK float32
  run smollm2-360m $SM $TASK float32
done
run qwen25-05b $Q25 gsm8k float16
run qwen3-06b $Q3 gsm8k bfloat16
echo done > $D/matrix.done
