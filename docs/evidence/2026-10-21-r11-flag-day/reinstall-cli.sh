#!/bin/bash
# Reinstall a CLI Worker home for the live lab, keeping its verified downloads and model (owner request, 2026-10-21).
# Usage: ssh <host> 'bash -s -- <old agent pid> [wsl]' < reinstall-cli.sh
set -uo pipefail
pid="${1:-}"
[ "${2:-}" = wsl ] && export LD_LIBRARY_PATH=/usr/lib/wsl/lib  # WSL: Ubuntu NVIDIA libraries shadow the Windows driver
if [ -n "$pid" ] && [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q "worker_cli run"; then
  kill "$pid"; sleep 5; echo "stopped old agent $pid"
fi
for entry in /proc/[0-9]*/cmdline; do
  if tr '\0' ' ' < "$entry" 2>/dev/null | grep -q "share/heteroes-worker/runtimes/.*worker_cli"; then
    echo "a Worker process of this home is still running: $entry"; exit 1
  fi
done
cd "$HOME/.local/share/heteroes-worker" || exit 1
rm -rf -- bundle runtimes device-token settings.json agent-config.json agent-state artifacts install-backups
echo "kept: $(ls)"
until curl -fsSL https://lab.heteroes.site/downloads/install-worker.sh | bash; do echo "--- retry in 5 s"; sleep 5; done
"$HOME/.local/bin/heteroes-worker" selftest
"$HOME/.local/bin/heteroes-worker" status
df -h "$HOME" | tail -1
