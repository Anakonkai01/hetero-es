#!/bin/bash
# Put the live lab back on r11 candidate9 (93ff85f) with the database as it was when deploy-lab.sh stopped it.
#   ! bash docs/evidence/2026-10-22-fix-wave1/deploy-lab-rollback.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
exec > >(tee -a "$HERE/deploy-lab-rollback.log") 2>&1
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
STATE=$HOME/.config/heteroes-m2/state
BACKUP=/mnt/Archive-2tb/heteroes-local/backups/fix-wave1-20261022
echo "=== $(date -Is) rollback"
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
mv "$STATE/product.sqlite" "$STATE/product-fix-wave1-rolled-back-$(date +%Y%m%d-%H%M%S).sqlite"
rm -f "$STATE/product.sqlite-wal" "$STATE/product.sqlite-shm"
cp "$BACKUP/product-at-stop.sqlite" "$STATE/product.sqlite" && chmod 600 "$STATE/product.sqlite"
git -C "$APP" checkout -q --detach 93ff85f28651988a484be69383f0e78cc6c78d0d
rm -rf "$APP/frontend/dist" && mv "$APP/frontend/dist-r11c9" "$APP/frontend/dist"
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
echo "=== $(date -Is) rolled back (installer links of the new build stay; publish the candidate9 receipt to restore them)"
