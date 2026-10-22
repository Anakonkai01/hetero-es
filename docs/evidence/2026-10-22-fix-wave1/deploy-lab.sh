#!/bin/bash
# Switch the live lab from r11 candidate9 (93ff85f) to the fix-wave1 build. Run by the owner (the Claude Code permission
# classifier refuses stopping the live lab):   ! bash docs/evidence/2026-10-22-fix-wave1/deploy-lab.sh
# Undo: deploy-lab-rollback.sh. Writes a log next to this file.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
exec > >(tee -a "$HERE/deploy-lab.log") 2>&1
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
BUILD=lf1-20261022-r11-candidate10
PACKAGES=/mnt/Archive-2tb/heteroes-local/downloads/$BUILD
COMMIT=41dc450
BACKUP=/mnt/Archive-2tb/heteroes-local/backups/fix-wave1-20261022
echo "=== $(date -Is) deploy $COMMIT ($BUILD)"
[ "$(git -C "$APP" rev-parse HEAD)" = 93ff85f28651988a484be69383f0e78cc6c78d0d ] || { echo "live copy is not at 93ff85f"; exit 1; }
"$PY" - <<'EOF'
import sqlite3, pathlib
db = sqlite3.connect(f"file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro", uri=True)
n = sum(db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("device_reservations", "physical_reservations"))
assert n == 0, f"{n} reservations: the lab is not idle"
print("lab idle: no reservations")
EOF
# 1. stop, then a final consistent copy of the database (written after the stop)
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
"$PY" -c "
import sqlite3, pathlib
src = sqlite3.connect(f'file:{pathlib.Path.home()}/.config/heteroes-m2/state/product.sqlite?mode=ro', uri=True)
dst = sqlite3.connect('$BACKUP/product-at-stop.sqlite'); src.backup(dst); dst.close(); print('database copied at stop')"
chmod 600 "$BACKUP/product-at-stop.sqlite"
# 2. code and web
git -C "$APP" fetch -q origin feat/gsm8k-demo
git -C "$APP" checkout -q --detach "$COMMIT"
mv "$APP/frontend/dist" "$APP/frontend/dist-r11c9"
cp -a "$PACKAGES/web" "$APP/frontend/dist"
diff -rq "$PACKAGES/web" "$APP/frontend/dist" && echo "web build in place"
# 3. start (the schema migration adds devices.keep_on)
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
sleep 5
curl -fsS https://lab.heteroes.site/api/v1/health | head -c 300; echo
# 4. installers: Windows apps and the CLI of this build on the download page
"$PY" -I "$APP/scripts/publish-local-installers.py" --packages "$PACKAGES" --build "$BUILD" \
  --receipt "$HERE/installers-prepared.json" --prepare-only
"$PY" -I "$APP/scripts/publish-local-installers.py" --packages "$PACKAGES" --build "$BUILD" \
  --receipt "$HERE/installers-published.json" --prepared-receipt "$HERE/installers-prepared.json"
curl -fsS https://lab.heteroes.site/downloads/manifest.json | head -c 400; echo
echo "=== $(date -Is) done"
