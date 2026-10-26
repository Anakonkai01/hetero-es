#!/bin/bash
# Build the 3060 stage archive from commits (new = HEAD, base = <base commit>) plus this folder's harness.
# Usage: stage.sh <out.tar.gz> <base commit>   (run from the repository root)
set -euo pipefail
out=$1; base=$2; work=$(mktemp -d .scratch/stage-3060-XXXX)
mkdir -p $work/new $work/base
git archive HEAD runtime/src runtime/tests runtime/scripts/benchmark_inference.py runtime/scripts/probe_strict_backend.py | tar -x -C $work/new --strip-components=1
git archive $base runtime/src | tar -x -C $work/base --strip-components=1
H=docs/evidence/2026-10-26-strict-prefill-attention/harness
cp $H/probe_projection_parity.py $H/bench_single.py $H/remote_3060.sh $work/
cp docs/evidence/2026-10-26-vllm-impact/workload-chat-01.json $work/
git rev-parse HEAD > $work/new/COMMIT; git rev-parse $base > $work/base/COMMIT
(cd $work && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -czf $out -C $work .
rm -rf $work
sha256sum $out
