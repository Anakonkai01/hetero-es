#!/usr/bin/env bash
# Build the Worker and Lab Server apps for Linux (unpacked) and Windows (NSIS, through Wine) into a FRESH
# directory. It never replaces an existing build, because published installers and evidence refer to them.
#
#   BUILD=lf1-20261012-r5 scripts/build-apps.sh
#
# Steps: build the Web UI into $OUT/web (the lab's own frontend/dist is not touched), refresh the packaged runtimes
# from Track A (updates desktop/*/resources/{runtime.tar.gz,profile.json}: commit them), type-check and bundle each
# app, package. Afterwards verify and publish:
#   scripts/check-linux-server.cjs / scripts/check-linux-packaged.cjs --phase install   (see docs/session-handoff-2026-10-12-lf1.md)
#   python3 scripts/publish-local-installers.py --packages $OUT --build $BUILD --receipt docs/evidence/<folder>/installers-<build>.json
set -euo pipefail
: "${BUILD:?Set BUILD to a new name such as lf1-20261012-r5}"
ROOT="${DOWNLOADS:-/mnt/Archive-2tb/heteroes-local/downloads}"
OUT="$ROOT/$BUILD"
TRACK_A="${TRACK_A:-$(cd "$(dirname "$0")/.." && pwd)/runtime}"
cd "$(dirname "$0")/.."
findmnt -n -o UUID -T "$ROOT" | grep -qx "${ARCHIVE_UUID:-10443D1F443D094C}" || { echo "The Archive disk is not mounted at $ROOT" >&2; exit 1; }
[ ! -e "$OUT" ] || { echo "$OUT already exists; choose a new BUILD name" >&2; exit 1; }
mkdir -p "$OUT"
echo "=== web $(date +%T)"
npm run build --workspace frontend -- --outDir "$OUT/web" --emptyOutDir
echo "=== runtimes $(date +%T)"
python3 -I scripts/refresh-worker-runtime.py --track-a "$TRACK_A"
python3 -I scripts/refresh-server-runtime.py --web "$OUT/web"
# The Worker offers this lab address on first start and shows the build name in its footer (commit the file afterwards).
printf '{"labUrl":"%s","build":"%s"}\n' "${DEFAULT_LAB_URL:-https://lab.heteroes.site}" "$BUILD" > desktop/worker/resources/defaults.json
for app in worker server; do
  echo "=== $app: type check and bundle $(date +%T)"
  npm run build --workspace "@heteroes/$app"
  echo "=== $app: Linux unpacked $(date +%T)"
  (cd "desktop/$app" && npx electron-builder --linux dir --x64 --publish never --config.directories.output="$OUT/$app")
done
for app in worker server; do
  echo "=== $app: Windows installer (Wine, unsigned) $(date +%T)"
  (cd "desktop/$app" && npx electron-builder --win nsis --x64 --publish never --config.directories.output="$OUT/$app")
done
echo "=== done $(date +%T): $OUT"
git status --short desktop/*/resources
