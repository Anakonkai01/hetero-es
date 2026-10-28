#!/bin/bash
set -eu
cd "$(dirname "$0")"
unset ELECTRON_RUN_AS_NODE
export XDG_CONFIG_HOME=$PWD/xdg/config XDG_DATA_HOME=$PWD/xdg/data HETEROES_GPU_ACCEPTANCE=1
exec dbus-run-session -- xvfb-run -a node ../worker.cjs --executable /mnt/Archive-2tb/heteroes-local/downloads/lf1-20261021-r11-candidate8/worker/linux-unpacked/heteroes-worker --dir "$PWD"
