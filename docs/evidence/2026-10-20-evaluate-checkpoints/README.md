# Checkpoint evaluation by replay for local v3 runs — 2026-10-20

`runtime/scripts/v3_evaluate_checkpoints.py RUN_DIR --model-path M --generations -1,9,29 --split validation --out R`:
the coordinator keeps only recent weights, so each requested checkpoint is rebuilt from the base model by replaying
the ledger's update records (any coefficient rule or momentum: `record.update_inputs()`), and every replayed
generation must hash to the child the ledger recorded. Each checkpoint is scored on the chosen split with the run's
own evaluation (greedy, prompt, token budget, precision, `evaluation.chunk`) and plan scorer (a python scorer needs
`--scorer-path` and `--scorer-function` matching the pinned hash): mean reward, score counts, truncations, mean
characters and all outputs.

Tests `runtime/tests/v3/test_v3_evaluate_checkpoints.py` (tiny CPU model): replayed hashes equal the run's children;
the base checkpoint equals an independent evaluation of the fresh model; a replay that does not reach the recorded
child is refused. Mutation 5/5 killed (first run: the hash check survived; a test now breaks the replay).

## What this does NOT show

- Replay uses the CPU-engine update (`apply_coefficients_`); runs made with the CUDA noise engine are not supported by
  this script yet.
- No GPU evaluation is recorded here.
