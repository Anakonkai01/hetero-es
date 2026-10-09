#!/usr/bin/env bash
# B0 and T2 (the 5070 Ti, then the 5070 Ti + the first 3060) with the DEFAULT decode engine of a long workload, which is now the compacting decoder (no --decode-engine option given), in the same session.
# N = 24, 3 generations, cot_l1_q128, CUDA engine, FP32, chunk 64, experiment id c1v2, replay always on the 3060. Compare with ../2026-10-09-dispatch-3060 (T2 with generate(): 116.5 s) and ../2026-10-09-decode-engine-b0.
# The profiles passed are those measured with generate(): they are used for the prediction only, which is therefore not to be trusted here.
set -uo pipefail
D=artifacts/experiments/2026-10-09-t2-compact
C=artifacts/experiments/2026-10-08-c1-v2
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
PYTHONPATH=src $PY scripts/run_benchmark.py --out-dir $D/bench --repeats 2 --conditions B0,T2 \
 --candidates 24 --generations 3 --chunk 64 --eval-dtype float32 --noise-engine cuda --workload cot_l1_q128 --coordinator-noise-threads 28 --experiment-id c1v2 --run-timeout 3000 --local-python $PY \
 --profile-reference $C/profile-5070ti-l1q128-cuda.json --profile-candidate $C/profile-1660s-l1q128-cuda.json --profile-third artifacts/experiments/2026-10-08-third-machine-3060/profile-3060-l1q128-cuda.json \
 --bind-host 0.0.0.0 --third thao_nguyen@100.92.20.58 --third-url http://100.110.165.40:8765 --third-env LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811 \
 --third-replay always
echo done > $D/done
