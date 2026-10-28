#!/usr/bin/env bash
# web-onboarding.sh <repo> <port> <fresh out dir>: build the web app, start a fixture lab, run the onboarding contract.
set -u
REPO=$1; PORT=$2; OUT=$3
cd "$REPO"
WEB=$(mktemp -d)
(cd frontend && npx vite build --outDir "$WEB" --emptyOutDir > /dev/null 2>&1) || { echo build failed; exit 1; }
/home/pc5070ti/projects/heteroes/.venv-backend/bin/python scripts/serve-test-lab.py --web "$WEB" --port "$PORT" > "$WEB.lab.log" 2>&1 &
LAB=$!
trap 'kill $LAB 2>/dev/null; wait $LAB 2>/dev/null; rm -rf "$WEB" "$WEB.lab.log"' EXIT
for _ in $(seq 1 25); do sleep 1; curl -s -m 2 "http://127.0.0.1:$PORT/api/v1/health" > /dev/null && break; done
node scripts/check-web-onboarding.mjs "http://127.0.0.1:$PORT" "$OUT"
