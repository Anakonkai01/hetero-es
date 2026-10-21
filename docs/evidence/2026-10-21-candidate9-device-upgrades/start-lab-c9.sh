#!/bin/bash
set -eu
cd "$(dirname "$0")"
unset ELECTRON_RUN_AS_NODE
export XDG_CONFIG_HOME=$PWD/xdg/config XDG_DATA_HOME=$PWD/xdg/data
exec xvfb-run -a node serve.cjs --executable /mnt/Archive-2tb/heteroes-local/downloads/lf1-20261021-r11-candidate9/server/linux-unpacked/heteroes-server --dir "$PWD" --host 100.110.165.40 --port 8790
