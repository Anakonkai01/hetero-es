#!/bin/bash
# Candidate8 package checks, all scratch trees on the Archive volume (the system disk is small). Run from the repo root.
set -u
unset ELECTRON_RUN_AS_NODE
A=/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261021-r11-candidate8
E=docs/evidence/2026-10-21-r11-candidate8
S=/mnt/Archive-2tb/heteroes-local/scratch-c8
mkdir -p $S
echo "=== source-copy $(date +%T)"
.venv-backend/bin/python -I scripts/check-desktop-packaging.py --out $S/source-copy > $E/candidate8-source-copy.log 2>&1; echo "source-copy exit=$?"
cp $S/source-copy/*.json $E/source-copy-packaging.json 2>/dev/null
echo "=== packaged worker $(date +%T)"
mkdir -p $S/w-xdg-config $S/w-xdg-data
XDG_CONFIG_HOME=$S/w-xdg-config XDG_DATA_HOME=$S/w-xdg-data HETEROES_GPU_ACCEPTANCE=1 dbus-run-session -- xvfb-run -a \
  node scripts/check-linux-packaged.cjs --phase install --executable $A/worker/linux-unpacked/heteroes-worker --output $S/worker-out > $E/candidate8-packaged-worker.log 2>&1; echo "worker exit=$?"
cp $S/worker-out/packaged-linux-install.json $E/ 2>/dev/null
echo "=== packaged server $(date +%T)"
mkdir -p $S/s-xdg-config $S/s-xdg-data
XDG_CONFIG_HOME=$S/s-xdg-config XDG_DATA_HOME=$S/s-xdg-data xvfb-run -a \
  node scripts/check-linux-server.cjs --executable $A/server/linux-unpacked/heteroes-server --output $S/server-out > $E/candidate8-packaged-server.log 2>&1; echo "server exit=$?"
cp $S/server-out/packaged-linux-server.json $E/ 2>/dev/null
echo "=== done $(date +%T)"
