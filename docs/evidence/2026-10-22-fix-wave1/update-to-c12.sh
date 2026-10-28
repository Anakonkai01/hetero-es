#!/bin/bash
# Update a CLI Worker service from candidate10/11 to candidate12 (bundle and installer in $1). One-time migration: the
# candidate10 runtime d5fa6d62a2c7 was installed from the same pinned lock file (sha256 d417ad4a…, checked equal in the
# candidate9/10/11 bundles), so it is marked with it and candidate12 links its packages instead of downloading them.
set -euo pipefail
dir="$1"
home="$HOME/.local/share/heteroes-worker"
echo d417ad4a35d642d159aef70fc8e9b27cd1cea14fa80094a0a53b06f1d5a60397 > "$home/runtimes/d5fa6d62a2c7/LOCK_SHA256"
rm -rf "$home/runtimes/bf6c6f6e38e6"  # candidate11, never finished on a full disk
systemctl --user stop heteroes-worker.service
HETEROES_SKIP_SETUP=1 HETEROES_BUNDLE=$(ls "$dir"/heteroes-worker-linux-*.tar.gz) bash "$dir/install-worker.sh"
"$HOME/.local/bin/heteroes-worker" selftest
systemctl --user start heteroes-worker.service
sleep 20
"$HOME/.local/bin/heteroes-worker" status
df -h "$HOME" | tail -1
