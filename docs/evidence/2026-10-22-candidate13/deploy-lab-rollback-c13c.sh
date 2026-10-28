#!/bin/bash
# Back from the lab-only update to candidate13 (948059b). No schema change.
set -euo pipefail
APP=$HOME/.local/share/heteroes-lab/app
PY=$HOME/.local/share/heteroes-lab/venv-backend/bin/python
"$PY" -I "$APP/scripts/local-lab.py" stop --python "$PY"
git -C "$APP" checkout -q --detach 948059b
rm -rf "$APP/frontend/dist" && mv "$APP/frontend/dist-c13" "$APP/frontend/dist"
"$PY" -I "$APP/scripts/local-lab.py" start --python "$PY"
