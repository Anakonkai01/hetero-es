#!/usr/bin/env bash
# T2 with the SECOND borrowed 3060 (another city; WSL2; reaches the 5070 Ti through Tailscale, relay "sin") instead of the first 3060.
# Same experiment id, settings and N = 24 as ../2026-10-09-three-machines, so the final weights must equal those of its B0 runs.
# The admission profile used is the one of the FIRST 3060 (same GPU model; the second 3060 was not profiled for speed). The 3060 catches up by replay (always).
set -uo pipefail
D=artifacts/experiments/2026-10-09-remote-3060b
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench --repeats 1 --conditions T2 \
 --candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY \
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --profile-third artifacts/experiments/2026-10-08-third-machine-3060/profile-3060-l1q128-cuda.json \
 --bind-host 0.0.0.0 --third worker-user-b@100.64.0.2 --third-url http://100.110.165.40:8765 --third-env LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811 \
 --third-replay always
