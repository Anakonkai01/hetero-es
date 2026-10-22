#!/bin/bash
# Live lab: candidate12 (c472d2a) -> candidate12 + the (b2) fix (a198cb0 = b5e1bc7 cherry-picked, branch deploy/candidate13).
# Backend only: the web build, the installers and the agents stay candidate12. If the classifier refuses it, the owner runs:
#   ! bash docs/evidence/2026-10-22-tier3/deploy-lab-c13.sh
# Undo: check out c472d2a again and restart. Writes a log next to this file.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
exec > >(tee -a "$HERE/deploy-lab-c13.log") 2>&1
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
COMMIT=a198cb0
BACKUP=/mnt/Archive-2tb/heteroes-local/backups/c13-20261022
echo "=== $(date -Is) deploy $COMMIT (candidate12 + b2 fix)"
[ "$(git -C "$APP" rev-parse --short=7 HEAD)" = c472d2a ] || { echo "live copy is not at c472d2a"; exit 1; }
"$PY" - <<'EOF'
import sqlite3, pathlib
db = sqlite3.connect(f"file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro", uri=True)
n = sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("device_reservations", "physical_reservations"))
assert n == 0, f"{n} reservations: the lab is not idle"
print("lab idle: no reservations")
EOF
# 1. stop, then a consistent copy of the database
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
"$PY" -c "
import sqlite3, pathlib
src = sqlite3.connect(f'file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro', uri=True)
dst = sqlite3.connect('$BACKUP/product-at-stop-c13.sqlite'); src.backup(dst); dst.close(); print('database copied at stop')"
chmod 600 "$BACKUP/product-at-stop-c13.sqlite"
# 2. code (web unchanged)
git -C "$APP" fetch -q origin deploy/candidate13
git -C "$APP" checkout -q --detach "$COMMIT"
git -C "$APP" diff --stat c472d2a "$COMMIT"
# 3. start
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
sleep 5
curl -fsS https://lab.heteroes.site/api/v1/health | head -c 300; echo
echo "=== $(date -Is) done"
