#!/bin/bash
# Update a paired CLI Worker in place to a new build, keeping its pairing, model and verified downloads, then let
# `heteroes-worker setup` install the systemd service and turn contribution ON (kept after restarts).
# Usage (bundle and installer copied next to it first):
#   ssh <host> 'bash -s -- <dir with install-worker.sh and bundle> [sudo-password-file]' < update-cli.sh
set -uo pipefail
dir="$1"
bundle=$(ls "$dir"/heteroes-worker-linux-*.tar.gz)
# 1. stop the old agent of this home, however it was started (terminal, nohup): SIGINT drains like Ctrl-C
for entry in /proc/[0-9]*/cmdline; do
  if tr '\0' ' ' < "$entry" 2>/dev/null | grep -q "share/heteroes-worker/runtimes/.*worker_cli run"; then
    pid=$(basename "$(dirname "$entry")")
    kill -INT "$pid" && echo "asked agent $pid to stop"
    for _ in $(seq 1 120); do [ -d "/proc/$pid" ] || break; sleep 1; done
    [ -d "/proc/$pid" ] && { echo "agent $pid still running after 120 s"; exit 1; }
  fi
done
# 2. the new runtime (the old one stays on disk for a rollback: point the launcher back at it)
HETEROES_SKIP_SETUP=1 HETEROES_BUNDLE="$bundle" HETEROES_DOWNLOADS=https://lab.heteroes.site/downloads \
  bash "$dir/install-worker.sh" || exit 1
# 3. the GPU against the new runtime, then service + ON
"$HOME/.local/bin/heteroes-worker" selftest || exit 1
if [ -n "${2:-}" ] && ! loginctl show-user "$USER" -p Linger | grep -q yes; then
  sudo -S loginctl enable-linger "$USER" < "$2" && echo "linger on (service starts at boot)"
fi
"$HOME/.local/bin/heteroes-worker" setup --lab https://lab.heteroes.site --yes --on --keep --approval-timeout 60
"$HOME/.local/bin/heteroes-worker" status
