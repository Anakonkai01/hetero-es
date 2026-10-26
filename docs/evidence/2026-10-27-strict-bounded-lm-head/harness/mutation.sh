#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
while kill -0 3844369 2>/dev/null; do sleep 3; done
mkdir -p .scratch/codex-20261027-bound/mutations
python3 -u scripts/mutation-check.py --repo .scratch/codex-20261027-bound/stage/new --copy src --copy tests --env HETEROES_GPU_ACCEPTANCE=1 --env PYTHONPATH=src --test "/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/eval/test_integer_lm_head.py -k 'not instruction_audit and not wide_graph and not entire_admitted_exponent_range and not 32768'" --mutants docs/evidence/2026-10-27-strict-bounded-lm-head/harness/mutants-01.json --scratch .scratch/codex-20261027-bound/mutations > docs/evidence/2026-10-27-strict-bounded-lm-head/raw/mutation-01.log 2>&1
