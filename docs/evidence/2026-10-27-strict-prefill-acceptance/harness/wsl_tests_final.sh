#!/bin/bash
set -euo pipefail
cd /home/pc5070ti/projects/heteroes-codex-frozen-perf
while kill -0 3028458 2>/dev/null; do sleep 5; done
ssh -F /home/pc5070ti/.ssh/config -o BatchMode=yes -o ConnectTimeout=8 thao_nguyen@100.92.20.58 'cd /tmp/heteroes-codex-prefill-acceptance-20261027-01/new && test ! -e ../tests-3060-03.log && HETEROES_GPU_ACCEPTANCE=1 LD_LIBRARY_PATH=/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib PYTHONPATH=src:/tmp/heteroes-codex-testdeps-20261027-01 /home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12 -m pytest -q -p no:cacheprovider tests/eval/test_strict_*.py tests/eval/test_integer_*.py tests/eval/test_fp16_decoder_cuda.py > ../tests-3060-03.log 2>&1' || status=$?
ssh -F /home/pc5070ti/.ssh/config -o BatchMode=yes -o ConnectTimeout=8 thao_nguyen@100.92.20.58 'cat /tmp/heteroes-codex-prefill-acceptance-20261027-01/tests-3060-03.log' > docs/evidence/2026-10-27-strict-prefill-acceptance/raw/tests-3060-03.log
exit "${status:-0}"
