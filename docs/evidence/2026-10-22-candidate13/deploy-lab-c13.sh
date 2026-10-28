#!/bin/bash
# Switch the live lab from candidate12 (a198cb0) to candidate13 ($1, the build commit). If the Claude Code permission
# classifier refuses stopping the live lab, the owner runs it:   ! bash docs/evidence/2026-10-22-candidate13/deploy-lab-c13.sh <commit>
# Undo: check out a198cb0 again and put frontend/dist-c12 back (deploy-lab-rollback-c13.sh). Writes a log next to this file.
set -euo pipefail
COMMIT=${1:?usage: deploy-lab-c13.sh <commit>}
HERE=$(cd "$(dirname "$0")" && pwd)
exec > >(tee -a "$HERE/deploy-lab-c13.log") 2>&1
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
BUILD=lf1-20261022-r11-candidate13
PACKAGES=/mnt/Archive-2tb/heteroes-local/downloads/$BUILD
BACKUP=/mnt/Archive-2tb/heteroes-local/backups/candidate13-20261022
echo "=== $(date -Is) deploy $COMMIT ($BUILD)"
[ "$(git -C "$APP" rev-parse --short=7 HEAD)" = a198cb0 ] || { echo "live copy is not at a198cb0"; exit 1; }
[ -f "$PACKAGES/web/index.html" ] && [ -f "$PACKAGES/web/notebooks/researcher.ipynb" ] || { echo "build incomplete"; exit 1; }
"$PY" - <<'EOF'
import sqlite3, pathlib
db = sqlite3.connect(f"file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro", uri=True)
n = sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("device_reservations", "physical_reservations"))
assert n == 0, f"{n} reservations: the lab is not idle"
print("lab idle: no reservations")
EOF
mkdir -p "$BACKUP"
# 1. stop, then a consistent copy of the database (written after the stop)
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
"$PY" -c "
import sqlite3, pathlib
src = sqlite3.connect(f'file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro', uri=True)
dst = sqlite3.connect('$BACKUP/product-at-stop-c13.sqlite'); src.backup(dst); dst.close(); print('database copied at stop')"
chmod 600 "$BACKUP/product-at-stop-c13.sqlite"
# 2. code and web (the web build carries the example notebook and the SDK wheel under /notebooks)
git -C "$APP" fetch -q origin feat/real-user-c13
git -C "$APP" checkout -q --detach "$COMMIT"
mv "$APP/frontend/dist" "$APP/frontend/dist-c12"
cp -a "$PACKAGES/web" "$APP/frontend/dist"
diff -rq "$PACKAGES/web" "$APP/frontend/dist" && echo "web build in place"
# 3. start (writes the Caddyfile of this commit: a signed public dataset upload may carry up to 64 MiB)
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
sleep 5
curl -fsS https://lab.heteroes.site/api/v1/health | head -c 300; echo
curl -fsS -o /dev/null -w "notebook %{http_code}\n" https://lab.heteroes.site/notebooks/researcher.ipynb
# 4. installers: Windows apps and the CLI of this build on the download page
"$PY" -I "$APP/scripts/publish-local-installers.py" --packages "$PACKAGES" --build "$BUILD" \
  --receipt "$HERE/installers-prepared-c13.json" --prepare-only
"$PY" -I "$APP/scripts/publish-local-installers.py" --packages "$PACKAGES" --build "$BUILD" \
  --receipt "$HERE/installers-published-c13.json" --prepared-receipt "$HERE/installers-prepared-c13.json"
curl -fsS https://lab.heteroes.site/downloads/manifest.json | head -c 400; echo
echo "=== $(date -Is) done"
