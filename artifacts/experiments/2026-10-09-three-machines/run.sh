#!/usr/bin/env bash
# The three machines: 5070 Ti (coordinator + worker), 1660S (cable) and the borrowed 3060 (WSL2, reached through Tailscale; its link to the 5070 Ti is the home wifi, about 20 Mbit/s measured).
# Conditions: B0 (5070 Ti alone), B3 (+ 1660S), T2 (+ 3060), T3 (all three); the 3060 catches up by the rule of its profile (auto); one T2 run with the 3060 downloading (never).
# --third-env: WSL2 of the 3060, where `apt install nvitop` (22:51 on 08/10) pulled in the Ubuntu NVIDIA 580 libraries; their ptxjitcompiler shadows the Windows driver's and CUDA segfaulted (the first attempt, kept as invalid-*).
# Same experiment id and settings as ../2026-10-08-c1-v2, so every run must end with the same weights as its B0 runs.
set -uo pipefail
D=artifacts/experiments/2026-10-09-three-machines
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
COMMON="--candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --profile-third artifacts/experiments/2026-10-08-third-machine-3060/profile-3060-l1q128-cuda.json
 --bind-host 0.0.0.0 --third thao_nguyen@100.92.20.58 --third-url http://100.110.165.40:8765 --third-env LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811"
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench --repeats 2 --conditions B0,B3,T2,T3 $COMMON \
    --third-replay auto --third-replay-profile /tmp/profile-3060-with-sync.json
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench-3060-downloads --repeats 1 --conditions T2 $COMMON --third-replay never
