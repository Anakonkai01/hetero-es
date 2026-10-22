#!/bin/bash
# Build candidate13 (scripts/build-apps.sh), then put the example notebook and the SDK wheel of this commit into the web
# build, served by the lab at /notebooks/ (the create page links them).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
export BUILD=lf1-20261022-r11-candidate13
OUT=/mnt/Archive-2tb/heteroes-local/downloads/$BUILD
scripts/build-apps.sh
mkdir -p "$OUT/web/notebooks"
cp runtime/notebooks/researcher.ipynb "$OUT/web/notebooks/"
"$HOME/miniforge3/envs/heteroes-match/bin/python" -m pip wheel --no-deps --no-build-isolation -q -w "$OUT/web/notebooks" runtime
ls -la "$OUT/web/notebooks"
