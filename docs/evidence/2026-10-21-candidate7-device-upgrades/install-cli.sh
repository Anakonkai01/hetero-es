#!/bin/bash
# Upgrade a stopped CLI Worker home from candidate6 to candidate7 over the private tailnet transport.
# Usage: WORKER_ROOT=... DISK=/mnt/c MIN_FREE=20000000000 bash install-cli.sh
set -euo pipefail
worker_root="${WORKER_ROOT:?}"
old_runtime="$worker_root/runtimes/aa74bad820b9"
[ -f "$old_runtime/READY.json" ]
# No old-runtime process may remain when replacing this disposable, reproducible software cache.
for entry in /proc/[0-9]*/cmdline; do
  [ -r "$entry" ] || continue
  if tr '\0' '\n' < "$entry" 2>/dev/null | grep -Fq "$old_runtime/"; then
    echo 'Old runtime still in use; refusing cache replacement' >&2; exit 1
  fi
done
available_before=$(df -B1 --output=avail "${DISK:?}" | tail -n1 | tr -d ' ')
[ "$available_before" -ge "${MIN_FREE:?}" ]
backup="$worker_root/install-backups/candidate6-before7-20261021"
mkdir -p "$backup"
[ ! -e "$backup/READY.json" ]
cp "$old_runtime/READY.json" "$backup/READY.json"
cp -a "$worker_root/bundle" "$backup/bundle"
printf 'before available bytes=%s; replacing stopped runtime bytes=%s\n' "$available_before" "$(du -sb "$old_runtime" | cut -f1)"
# Pinned wheels/models, private settings/device identity, artifacts and all run state remain in their own paths.
rm -rf -- "$old_runtime"
curl -fsSL http://100.110.165.40:8802/cli/install-worker.sh | HETEROES_WORKER_HOME="$worker_root" HETEROES_DOWNLOADS=http://100.110.165.40:8802/cli bash
printf 'after available bytes=%s\n' "$(df -B1 --output=avail "$DISK" | tail -n1 | tr -d ' ')"
ls "$worker_root/runtimes"
