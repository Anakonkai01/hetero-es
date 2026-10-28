#!/bin/bash
# Lab-only update after candidate13 (948059b): backend (device names on the live view), web build, SDK wheel/notebook.
# The agents' packaged runtimes are NOT touched (they stay on candidate13b). Owner runs:
#   ! bash docs/evidence/2026-10-22-candidate13/deploy-lab-c13c.sh <commit>
# Undo: deploy-lab-rollback-c13c.sh. Log next to this file.
set -euo pipefail
COMMIT=${1:?usage: deploy-lab-c13c.sh <commit>}
HERE=$(cd "$(dirname "$0")" && pwd)
exec > >(tee -a "$HERE/deploy-lab-c13c.log") 2>&1
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
WEB=/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261022-r11-candidate13c-web/web
BACKUP=/mnt/Archive-2tb/heteroes-local/backups/candidate13c-20261022
echo "=== $(date -Is) deploy $COMMIT (lab only)"
[ "$(git -C "$APP" rev-parse --short=7 HEAD)" = 948059b ] || { echo "live copy is not at 948059b"; exit 1; }
[ -f "$WEB/index.html" ] && [ -f "$WEB/notebooks/researcher.ipynb" ] || { echo "web build incomplete"; exit 1; }
"$PY" - <<'PYEOF'
import sqlite3, pathlib
db = sqlite3.connect(f"file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro", uri=True)
n = sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("device_reservations", "physical_reservations"))
assert n == 0, f"{n} reservations: the lab is not idle"
print("lab idle: no reservations")
PYEOF
mkdir -p "$BACKUP"
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
"$PY" -c "
import sqlite3, pathlib
src = sqlite3.connect(f'file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro', uri=True)
dst = sqlite3.connect('$BACKUP/product-at-stop-c13c.sqlite'); src.backup(dst); dst.close(); print('database copied at stop')"
chmod 600 "$BACKUP/product-at-stop-c13c.sqlite"
git -C "$APP" fetch -q origin feat/real-user-c13
git -C "$APP" checkout -q --detach "$COMMIT"
mv "$APP/frontend/dist" "$APP/frontend/dist-c13"
cp -a "$WEB" "$APP/frontend/dist"
diff -rq "$WEB" "$APP/frontend/dist" && echo "web build in place"
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
sleep 5
curl -fsS https://lab.heteroes.site/api/v1/health | head -c 300; echo
curl -fsS -o /dev/null -w "notebook %{http_code}\n" https://lab.heteroes.site/notebooks/researcher.ipynb
echo "=== $(date -Is) done"
