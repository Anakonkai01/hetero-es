#!/bin/bash
set -euo pipefail
worker_root="$HOME/.local/share/heteroes-worker"
[ ! -e "$worker_root" ] || { echo "worker home already exists; refusing" >&2; exit 1; }
printf 'before / available bytes=%s\n' "$(df -B1 --output=avail / | tail -n1 | tr -d ' ')"
curl -fsSL http://100.110.165.40:8802/cli/install-worker.sh | HETEROES_WORKER_HOME="$worker_root" HETEROES_DOWNLOADS=http://100.110.165.40:8802/cli bash
printf 'after / available bytes=%s\n' "$(df -B1 --output=avail / | tail -n1 | tr -d ' ')"
ls "$worker_root/runtimes"
sha256sum "$worker_root"/runtimes/*/src/heteroes/eval/cpu_guard.py
echo INSTALL_DONE
