#!/bin/bash
# usage: run_noise.sh HOST  (in the f13 copy dir)
RT=~/.local/share/heteroes-worker/runtimes/756272d28ef3; M=~/.local/share/heteroes-worker/models/7ae557604adf67be50417f59c2c2f167def9a775
export CUDA_VISIBLE_DEVICES= PYTHONPATH=$RT/src
$RT/python/bin/python diag_noise.py . $M 118 3763230322833629 n118-$1.json --repeat 3 2>&1 | grep -v Loading
$RT/python/bin/python diag_noise.py . $M 284 1129624276068623 n284-$1.json --repeat 3 2>&1 | grep -v Loading
true
