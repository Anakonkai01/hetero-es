#!/usr/bin/env bash
# The night of 08/10 to 09/10, in order, without anyone present:
#   1. wait for the failure campaign x3 (short workload) to end;
#   2. kill-worker / pause-worker x3 on the long workload;
#   3. take the synchronization of the 3060 (measured by scripts/measure_sync.py through Tailscale), make the profile with that block (a DERIVED file, named so), put it on the 3060;
#   4. write the predictions BEFORE the runs (predict_cluster.py: the 3060 by replay and by download);
#   5. the three-machine runs.
set -uo pipefail
cd ~/projects/hetero-es
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
T=artifacts/experiments/2026-10-09-three-machines
M=artifacts/experiments/2026-10-08-third-machine-3060
C=artifacts/experiments/2026-10-08-c1-v2
echo "$(date) waiting for the failure campaign"
while pgrep -f "failure-campaign-x3/[r]un.sh" > /dev/null; do sleep 30; done
echo "$(date) stage 2: long-workload worker scenarios"
bash artifacts/experiments/2026-10-08-failure-campaign-long-workers/run.sh > artifacts/experiments/2026-10-08-failure-campaign-long-workers/run.out 2>&1
echo "$(date) stage 3: synchronization of the 3060"
for i in $(seq 1 120); do ssh -n thao_nguyen@100.92.20.58 'test -f /tmp/sync-3060-tailscale.json' && break; sleep 30; done
scp -q thao_nguyen@100.92.20.58:/tmp/sync-3060-tailscale.json $M/sync-3060-through-tailscale-wifi.json || echo "NO SYNC FILE"
pkill -f "scripts/[s]erve_weights" || true
$PY - <<'PYEOF'
import json
M = "artifacts/experiments/2026-10-08-third-machine-3060"
profile = json.load(open(f"{M}/profile-3060-l1q128-cuda.json"))
sync = json.load(open(f"{M}/sync-3060-through-tailscale-wifi.json"))["sync"]
profile["sync"] = sync
profile["derived"] = "profile-3060-l1q128-cuda.json with the sync block of sync-3060-through-tailscale-wifi.json (scripts/measure_sync.py), added by hand: the profile run had no sync server"
json.dump(profile, open(f"{M}/profile-3060-l1q128-cuda-with-sync.json", "w"), indent=2)
PYEOF
scp -q $M/profile-3060-l1q128-cuda-with-sync.json thao_nguyen@100.92.20.58:/tmp/profile-3060-with-sync.json
echo "$(date) stage 4: predictions"
PYTHONPATH=src $PY scripts/predict_cluster.py --candidates 24 --chunk 64 --out $T/prediction-3060-by-replay.json \
  --worker $C/profile-5070ti-l1q128-cuda.json --worker $C/profile-1660s-l1q128-cuda.json --worker $M/profile-3060-l1q128-cuda-with-sync.json:replay
PYTHONPATH=src $PY scripts/predict_cluster.py --candidates 24 --chunk 64 --out $T/prediction-3060-by-download.json \
  --worker $C/profile-5070ti-l1q128-cuda.json --worker $C/profile-1660s-l1q128-cuda.json --worker $M/profile-3060-l1q128-cuda-with-sync.json
echo "$(date) stage 5: three machines"
bash $T/run.sh > $T/run.out 2>&1
echo "$(date) done"
