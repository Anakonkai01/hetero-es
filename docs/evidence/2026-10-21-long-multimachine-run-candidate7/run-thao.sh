#!/bin/bash
# Reads the lab user access token from stdin (never argv), then offers the experiment through the installed CLI.
set -eu
read -r HETEROES_LAB_ACCESS_TOKEN; export HETEROES_LAB_ACCESS_TOKEN
H=$HOME/.local/share/heteroes-c4-cpu
R=$H/runtimes/57b0faf6d31a
test -x "$R/python/bin/python3.12"
test -f "$R/src/heteroes/product/membership.py"
cd /tmp/heteroes-r11-c7
export HETEROES_WORKER_HOME=$H PYTHONPATH=$R/src PYTHONNOUSERSITE=1 PYTHONUTF8=1 CUDA_VISIBLE_DEVICES=
exec $R/python/bin/python3.12 -s -m heteroes.v3 serve spec.json --lab http://100.110.165.40:8790 \
  --workspace bcbece5a24834ac28e358fc49db1343f --host 100.92.20.58 --worker-ids desktop-906949218c43,desktop-9f9da13f0f82 \
  --device cpu --worker-home $H --out /tmp/heteroes-r11-c7/offer
