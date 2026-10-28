#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
while kill -0 3871260 2>/dev/null; do sleep 3; done
HETEROES_GPU_ACCEPTANCE=1 /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python docs/evidence/2026-10-27-strict-prefill-m64/harness/tiles.py --gpu --src .scratch/codex-20261027-bound/stage/new/src --out docs/evidence/2026-10-27-strict-prefill-m64/raw/tiles-base-01.json > docs/evidence/2026-10-27-strict-prefill-m64/raw/tiles-base-01.log 2>&1
HETEROES_GPU_ACCEPTANCE=1 /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python docs/evidence/2026-10-27-strict-prefill-m64/harness/tiles.py --gpu --src .scratch/codex-20261027-ldsm/src --out docs/evidence/2026-10-27-strict-prefill-m64/raw/tiles-ldsm-01.json > docs/evidence/2026-10-27-strict-prefill-m64/raw/tiles-ldsm-01.log 2>&1
