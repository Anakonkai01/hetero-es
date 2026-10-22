#!/bin/bash
# Update a CLI Worker service to candidate13 (bundle and installer in $1). The runtime of candidate12 stays until the
# new one passes its self-test (the installer links the pinned packages it already has).
set -euo pipefail
dir="$1"
systemctl --user stop heteroes-worker.service
HETEROES_SKIP_SETUP=1 HETEROES_BUNDLE=$(ls "$dir"/heteroes-worker-linux-*.tar.gz) bash "$dir/install-worker.sh"
"$HOME/.local/bin/heteroes-worker" selftest
systemctl --user start heteroes-worker.service
sleep 20
"$HOME/.local/bin/heteroes-worker" status
df -h "$HOME" | tail -1
