#!/usr/bin/env bash
# The failure campaign with the SECOND borrowed 3060 (another city, WSL2, through Tailscale) as the disturbed remote worker (--remote-worker third).
# Long workload (cot_l1_q128, CUDA engine, chunk 64, N = 8, 3 generations) as ../2026-10-08-failure-campaign-long-workers. Scenarios: kill-worker, pause-worker, cut-link
# (packets from the 3060's Tailscale address dropped on the 5070 Ti, needs sudo: HETEROES_SUDO_PASSWORD in the environment, never in this file), kill-coordinator, kill-coordinator-mid-update.
# Order (the friend takes the 3060 back tonight, time unknown): rep1, then the speed/exactness profile of the 3060 (own GPU, so it cannot run beside the campaign), then rep2 and rep3.
set -uo pipefail
D=artifacts/experiments/2026-10-09-failure-campaign-remote-3060b
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
ENVV="LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811"
campaign() {
  PYTHONPATH=src $PY scripts/failure_campaign.py --out-dir $D/rep$1 --candidates 8 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 \
    --scenarios kill-worker,pause-worker,cut-link,kill-coordinator,kill-coordinator-mid-update --coordinator-noise-threads 28 --lease-seconds 60 --run-timeout 1800 --local-python $PY \
    --remote-worker third --bind-host 0.0.0.0 --third worker-user-b@100.64.0.2 --third-url http://100.110.165.40:8765 --third-env "$ENVV" --third-replay always
}
campaign 1
ssh worker-user-b@100.64.0.2 "cd ~/projects/heteroes/hetero-es && rm -f /tmp/c128/profile-3060b.json* && $ENVV PYTHONPATH=src ~/heteroes-venv/bin/python scripts/profile_worker.py --model-path \$HOME/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775 --worker-id worker-3060b --workload cot_l1_q128 --noise-engine cuda --chunks 1,64,128 --probe-candidates 8 --candidates 3 --out /tmp/c128/profile-3060b.json" > $D/profile-3060b.log 2>&1
scp -q worker-user-b@100.64.0.2:/tmp/c128/profile-3060b.json $D/ 
campaign 2
campaign 3
