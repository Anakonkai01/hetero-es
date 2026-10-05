#!/bin/sh
cd "$(dirname "$0")"
python learn.py --alpha 3e-3 --generations 10 --output run_alpha3e-3.json > run_alpha3e-3.log 2>&1
python learn.py --alpha 1e-3 --generations 10 --output run_alpha1e-3.json > run_alpha1e-3.log 2>&1
echo ALLDONE > run_all.done
