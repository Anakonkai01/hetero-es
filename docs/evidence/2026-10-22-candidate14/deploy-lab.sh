#!/usr/bin/env bash
# Authorized candidate14b deployment. No unit/process signals outside local-lab.py.
set -euo pipefail
DEPLOY_COMMIT=${1:?usage: deploy-lab.sh <reviewed source commit>}
DEPLOY_REPO=$(cd "$(dirname "$0")/../../.." && pwd)
DEPLOY_APP=$HOME/.local/share/heteroes-lab/app
DEPLOY_PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
DEPLOY_BUILD=lf1-20261022-r11-candidate14b
DEPLOY_PACKAGES=/mnt/Archive-2tb/heteroes-local/downloads/$DEPLOY_BUILD
DEPLOY_EVIDENCE=$DEPLOY_REPO/docs/evidence/2026-10-22-candidate14
DEPLOY_BACKUP=$HOME/.local/share/heteroes-lab/backups/candidate14-20261022
[ "$(git -C "$DEPLOY_APP" rev-parse --short=7 HEAD)" = 2047452 ]
git -C "$DEPLOY_APP" diff --quiet
git -C "$DEPLOY_APP" diff --cached --quiet
findmnt -n -o UUID -T "$DEPLOY_PACKAGES" | rg -qx 10443D1F443D094C
[ -f "$DEPLOY_PACKAGES/web/notebooks/heteroes-0.0.1-py3-none-any.whl" ]
[ ! -e "$DEPLOY_BACKUP" ]
"$DEPLOY_PY" - <<'PY'
from pathlib import Path
import sqlite3
with sqlite3.connect('file:'+str(Path.home()/'.config/heteroes-m2/state/product.sqlite')+'?mode=ro',uri=True) as db:
    for table in ('queue','device_reservations','physical_reservations','model_probe_reservations'):
        assert db.execute('SELECT count(*) FROM '+table).fetchone()[0] == 0, table+' is not idle'
print('Idle queue and all physical/device/probe reservations confirmed')
PY
mkdir -m 700 -p "$DEPLOY_BACKUP"
git -C "$DEPLOY_APP" fetch -q "$DEPLOY_REPO" feat/real-user-c13
[ "$(git -C "$DEPLOY_APP" rev-parse FETCH_HEAD)" = "$(git -C "$DEPLOY_REPO" rev-parse "$DEPLOY_COMMIT")" ]
"$DEPLOY_PY" -I "$DEPLOY_APP/scripts/local-lab.py" stop --python "$DEPLOY_PY"
"$DEPLOY_PY" - "$DEPLOY_BACKUP" <<'PY'
from pathlib import Path
import os,sqlite3,sys
p=Path(sys.argv[1])/'product-at-stop.sqlite'
with sqlite3.connect('file:'+str(Path.home()/'.config/heteroes-m2/state/product.sqlite')+'?mode=ro',uri=True) as src:
    with sqlite3.connect(p) as dst:src.backup(dst)
os.chmod(p,0o600)
print('Consistent private database backup saved')
PY
cp -a "$DEPLOY_APP/frontend/public/downloads/manifest.json" "$DEPLOY_BACKUP/installers-manifest.json"
mv "$DEPLOY_APP/frontend/dist" "$DEPLOY_BACKUP/frontend-dist"
git -C "$DEPLOY_APP" checkout -q --detach "$DEPLOY_COMMIT"
cp -a "$DEPLOY_PACKAGES/web" "$DEPLOY_APP/frontend/dist"
diff -rq "$DEPLOY_PACKAGES/web" "$DEPLOY_APP/frontend/dist"
"$DEPLOY_PY" -I "$DEPLOY_APP/scripts/local-lab.py" start --python "$DEPLOY_PY"
"$DEPLOY_PY" -I "$DEPLOY_APP/scripts/publish-local-installers.py" --packages "$DEPLOY_PACKAGES" --build "$DEPLOY_BUILD" \
  --receipt "$DEPLOY_EVIDENCE/installers-published.json" --prepared-receipt "$DEPLOY_EVIDENCE/installers-prepared-final.json"
"$DEPLOY_PY" -I "$DEPLOY_APP/scripts/local-lab.py" status
curl --retry 5 --retry-delay 2 --retry-all-errors -fsS https://lab.heteroes.site/api/v1/health
curl -fsS -o /dev/null -w 'researcher notebook HTTP %{http_code}\n' https://lab.heteroes.site/notebooks/researcher.ipynb
printf 'Deployed %s (%s)\n' "$DEPLOY_COMMIT" "$DEPLOY_BUILD"
