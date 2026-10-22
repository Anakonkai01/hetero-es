#!/bin/bash
RT=~/.local/share/heteroes-worker/runtimes/756272d28ef3; M=~/.local/share/heteroes-worker/models/7ae557604adf67be50417f59c2c2f167def9a775
export CUDA_VISIBLE_DEVICES= PYTHONPATH=$RT/src
mkdir -p c-$1; cp recipe.json c-$1/
$RT/python/bin/python diag_noise.py c-$1 $M 118 3763230322833629 c-$1/x.json --chunks 10,13 2>&1 | grep -v Loading
$RT/python/bin/python diag_noise.py c-$1 $M 284 1129624276068623 c-$1/y.json --chunks 6 2>&1 | grep -v Loading
true
