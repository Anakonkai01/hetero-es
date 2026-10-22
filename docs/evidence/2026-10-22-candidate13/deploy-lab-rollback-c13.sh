#!/bin/bash
# Back from candidate13 to candidate12 (a198cb0) if the acceptance fails. The database copy taken at the stop is in
# /mnt/Archive-2tb/heteroes-local/backups/candidate13-20261022 (candidate12 reads a candidate13 database: no schema change).
set -euo pipefail
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
git -C "$APP" checkout -q --detach a198cb0
rm -rf "$APP/frontend/dist" && mv "$APP/frontend/dist-c12" "$APP/frontend/dist"
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
