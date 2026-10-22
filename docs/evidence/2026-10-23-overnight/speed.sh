#!/usr/bin/env bash
set -u
cd /home/pc5070ti/projects/heteroes
E=docs/evidence/2026-10-23-overnight/speed
export HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src
PY=$HOME/miniforge3/envs/heteroes-match/bin/python
for spec in "3:5070ti-nhan,5070ti-nhut,3060-thao" "2:5070ti-nhan,5070ti-nhut" "1:5070ti-nhan"; do
  n=${spec%%:*}; w=${spec#*:}
  echo "=== $n machines $(date +%T)"
  $PY .scratch/overnight/submit-run.py --gpu --out $E/m$n --name "Overnight speed: $n machine(s)" \
    --namespace overnight-speed-2026-10-23 --workers $w --population 48 --generations 4 --batch 8 \
    --validation-interval 100 > $E/m$n.log 2>&1
  echo "exit $? $(date +%T)"; tail -2 $E/m$n.log
done
