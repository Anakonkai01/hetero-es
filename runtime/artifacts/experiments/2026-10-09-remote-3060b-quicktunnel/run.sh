#!/usr/bin/env bash
# T2 with the second borrowed 3060 reaching the coordinator through a Cloudflare QUICK TUNNEL (public https address, no tailnet).
# Usage: HETEROES_TOKEN=<random secret> TUNNEL_URL=https://....trycloudflare.com bash run.sh   (the secret is never written here)
# Differences from ../2026-10-09-remote-3060b/run.sh: the 3060 uses TUNNEL_URL; the coordinator and both workers use a token
# (cluster_runner starts the coordinator with --allow-unauthenticated, but a token that is set is still enforced and checked by the server).
set -uo pipefail
D=artifacts/experiments/2026-10-09-remote-3060b-quicktunnel
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
: "${HETEROES_TOKEN:?set HETEROES_TOKEN}" "${TUNNEL_URL:?set TUNNEL_URL}"
export HETEROES_TOKEN
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench --repeats 1 --conditions T2 \
 --candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY \
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --profile-third artifacts/experiments/2026-10-08-third-machine-3060/profile-3060-l1q128-cuda.json \
 --bind-host 0.0.0.0 --third worker-user-b@100.64.0.2 --third-url "$TUNNEL_URL" --third-env "LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811 HETEROES_TOKEN=$HETEROES_TOKEN" \
 --third-replay always
