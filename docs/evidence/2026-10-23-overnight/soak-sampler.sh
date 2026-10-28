#!/usr/bin/env bash
# Every 5 minutes: GPU memory and HeteroES process memory on the three machines (one JSON line each), until the run ends.
OUT=$1; RID=$2
while true; do
  t=$(date +%s)
  n=$(nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits | tr -d ' ')
  nr=$(ps -eo rss,args | grep -E "heteroes\.(product|v3)" | grep -v grep | awk '{s+=$1} END {print s}')
  h=$(ssh -o BatchMode=yes -o ConnectTimeout=8 heheboiz@100.108.195.50 'nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits | tr -d " "; ps -eo rss,args | grep -E "heteroes\.(product|v3)" | grep -v grep | awk "{s+=\$1} END {print s}"' 2>/dev/null | tr '\n' ' ')
  w=$(ssh -o BatchMode=yes -o ConnectTimeout=8 thao_nguyen@100.92.20.58 '/usr/lib/wsl/lib/nvidia-smi --query-gpu=memory.used,utilization.gpu,temperature.gpu --format=csv,noheader,nounits | tr -d " "' 2>/dev/null)
  wr=$(ssh -o BatchMode=yes -o ConnectTimeout=8 thao_nguyen@100.92.20.58 '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command "(Get-Process -Name \"HeteroES Worker\",python,pythonw -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum"' 2>/dev/null | tr -d '\r')
  echo "{\"t\":$t,\"nhanGpu\":\"$n\",\"nhanRssKb\":\"$nr\",\"nhut\":\"$h\",\"windowsGpu\":\"$w\",\"windowsWorkingSetBytes\":\"$wr\"}" >> "$OUT"
  s=$(python3 -c "import json;print(json.load(open('$HOME/.local/share/heteroes-worker/agent-state/runs/$RID/state.json'))['status'])" 2>/dev/null)
  case "$s" in COMPLETED|FAILED|CANCELLED) echo "{\"t\":$t,\"end\":\"$s\"}" >> "$OUT"; exit 0;; esac
  sleep 300
done
