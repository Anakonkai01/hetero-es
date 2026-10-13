#!/usr/bin/env bash
# One command for the whole CPU-only check suite, with evidence written to a FRESH directory:
#
#   scripts/check-all.sh docs/evidence/2026-10-13-ui/checks
#
# Runs: backend tests, frontend/Worker/Server unit tests, type checks, lint, i18n check, then the browser and Electron
# contracts against throwaway fixture labs (never the real lab, never a GPU). Set PYTHON to the backend interpreter
# (default ../Hetero-ES-LLM/.venv-backend/bin/python). It needs Chromium (Playwright), Xvfb and Node 24.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=${1:?usage: scripts/check-all.sh <fresh evidence directory>}
[ ! -e "$OUT" ] || { echo "$OUT already exists; choose a new directory" >&2; exit 2; }
PYTHON=${PYTHON:-../Hetero-ES-LLM/.venv-backend/bin/python}
mkdir -p "$OUT"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"; [ -n "${LAB:-}" ] && kill "$LAB" 2>/dev/null; true' EXIT
failed=()
step() { local name=$1; shift; printf '=== %s\n' "$name"; if "$@" > "$OUT/$name.log" 2>&1; then echo "PASS $name"; else echo "FAIL $name (see $OUT/$name.log)"; failed+=("$name"); fi; }

step backend-tests env CUDA_VISIBLE_DEVICES= "$PYTHON" -m pytest backend/tests -q
step frontend-unit bash -c 'cd frontend && node --test tests/*.test.mjs'
step worker-unit bash -c 'cd desktop/worker && node --test tests/*.test.cjs tests/*.test.mjs'
step server-unit bash -c 'cd desktop/server && node --test tests/*.test.cjs'
step product-ui-unit bash -c 'node --test packages/product-ui/tests/*.test.*'
step types bash -c 'cd frontend && npx tsc -b && cd ../desktop/worker && npx tsc --noEmit && cd ../server && npx tsc --noEmit'
step lint bash -c 'cd frontend && npx eslint src'
step i18n node scripts/check-i18n.mjs
step web-build bash -c "cd frontend && npx vite build --outDir '$WORK/web' --emptyOutDir"
step worker-build npm run build --workspace @heteroes/worker

lab() {   # lab <port> [extra serve-test-lab args...]
  local port=$1; shift
  "$PYTHON" scripts/serve-test-lab.py --web "$WORK/web" --port "$port" "$@" > "$WORK/lab-$port.log" 2>&1 &
  LAB=$!
  for _ in $(seq 1 25); do sleep 1; curl -s -m 2 "http://127.0.0.1:$port/api/v1/health" > /dev/null && return 0; done
  echo "fixture lab on $port did not start" >&2; return 1
}
stop_lab() { kill "$LAB" 2>/dev/null; wait "$LAB" 2>/dev/null; LAB=; }
SEEDS=(--seed-run backend/tests/fixtures/run-d09d6ea8.json --seed-run backend/tests/fixtures/run-95b34770.json)

lab 18090 && step web-onboarding node scripts/check-web-onboarding.mjs http://127.0.0.1:18090 "$OUT/web-onboarding"; stop_lab
lab 18091 "${SEEDS[@]}" --simulate-live backend/tests/fixtures/run-d09d6ea8.json && step web-live node scripts/check-web-live.mjs http://127.0.0.1:18091 "$OUT/web-live"; stop_lab
lab 18092 "${SEEDS[@]}" && step web-experiments node scripts/check-web-experiments.mjs http://127.0.0.1:18092 "$OUT/web-experiments"; stop_lab
lab 18093 "${SEEDS[@]}" && step web-showcase node scripts/check-web-showcase.mjs http://127.0.0.1:18093 "$OUT/web-showcase"; stop_lab
lab 18094 "${SEEDS[@]}" && step web-pages node scripts/audit-web-pages.mjs http://127.0.0.1:18094 "$OUT/web-pages" --credentials <(echo '{"users":{"admin":"test-admin-pass"}}') --matrix vi:light:1440,en:dark:375; stop_lab
step worker-onboarding xvfb-run -a node scripts/check-worker-onboarding.cjs "$OUT/worker-onboarding"
step worker-station xvfb-run -a node scripts/check-worker-station.cjs "$OUT/worker-station"

if [ ${#failed[@]} -eq 0 ]; then echo "ALL PASS"; else echo "FAILED: ${failed[*]}"; exit 1; fi
