#!/usr/bin/env bash
# cut-link while the second 3060 DOWNLOADS the new weights (988 MB over the real 21 Mbit/s link, --third-replay never): packets from its Tailscale address are dropped on the 5070 Ti
# 3 s after generation 0 is published (inside the download) for 15 s. Reference hash: the undisturbed run of ../2026-10-09-failure-campaign-remote-3060b/rep1 (same N, generations, workload, chunk, experiment id "campaign").
# HETEROES_SUDO_PASSWORD must be in the environment (never in this file).
set -uo pipefail
D=artifacts/experiments/2026-10-09-cutlink-download-3060b
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
PYTHONPATH=src $PY scripts/failure_campaign.py --out-dir $D/run --candidates 8 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 \
  --scenarios cut-link --cut-delay 3 --cut-seconds 15 --reference-final a2123e795488fd6dd82465e83f5825b0c44c933b1760ad26711052f8a9c3a1c8 --coordinator-noise-threads 28 --lease-seconds 60 --run-timeout 2400 --local-python $PY \
  --remote-worker third --bind-host 0.0.0.0 --third worker-user-b@100.64.0.2 --third-url http://100.110.165.40:8765 \
  --third-env "LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811" --third-replay never
