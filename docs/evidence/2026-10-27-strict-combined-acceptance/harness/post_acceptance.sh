#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
# This specific parent and its child GPU suite were confirmed live when this queue was created.
while kill -0 1925518 2>/dev/null; do sleep 3; done
python3 - <<'PY'
from pathlib import Path
s=Path('docs/evidence/2026-10-27-strict-combined-acceptance/raw/tests-5070ti-full-01.log').read_text().splitlines()[-1]
assert ' passed in ' in s and 'failed' not in s,s
PY
export HETEROES_GPU_ACCEPTANCE=1
PY=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
OUT=docs/evidence/2026-10-27-strict-reciprocal-table
PYTHONPATH=runtime/src:$OUT/harness "$PY" -m pytest -q "$OUT/harness/test_lookup_gpu.py" > "$OUT/raw/gpu-01.log" 2>&1
PYTHONPATH=runtime/src:$OUT/harness "$PY" "$OUT/harness/bench.py" --gpu --out "$OUT/raw/bench-01.json" > "$OUT/raw/bench-01.log" 2>&1
OUT=docs/evidence/2026-10-27-strict-prefill-occupancy
"$PY" "$OUT/harness/tiles.py" --gpu --src .scratch/codex-20261027-combined/stage/new/src --out "$OUT/raw/operators-01.json" > "$OUT/raw/operators-01.log" 2>&1
OUT=docs/evidence/2026-10-27-strict-combined-acceptance
python3 -u scripts/mutation-check.py --repo .scratch/codex-20261027-combined/stage/new --copy src --copy tests --env HETEROES_GPU_ACCEPTANCE=1 --env PYTHONPATH=src --test "$PY -m pytest -q tests/eval/test_integer_stream.py tests/eval/test_strict_graph_host.py -k '(tiles_match and 22) or reciprocal'" --mutants "$OUT/harness/mutants-gpu-01.json" --scratch .scratch/codex-20261027-combined/mutations > "$OUT/raw/mutation-gpu-01.log" 2>&1
