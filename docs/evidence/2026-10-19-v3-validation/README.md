# Recipe v3 validation and verified export

Source checkpoint: `ae96728`, following the product integration commit `c9eccfd`.

- The coordinator evaluates the validation split with the run's frozen declarative scorer at the configured interval, including the initial and final checkpoints. Selection maximizes mean reward and preserves the earlier checkpoint on ties. A persisted selection is bound to both recipe and plan hashes.
- Validation JSON, selection, metrics history and `validation_completed` events are persisted. The product generation projection includes validation rewards. Test data is read only at final export, after workers have stopped.
- Full/subset exports reload safetensors independently; LoRA exports reload with PEFT against the pinned base. The selected trainable-weight hash, raw test outputs and per-row scores must agree. Failed reloads leave test metrics locked and publish no verified receipt. Cached export files are checked again before reuse.
- Export tests perturb the selected weights, including nonzero LoRA adapters. `targeted-final.log`: 14 passed before two additional negative reload tests; the final mutation control includes all **7 tracker tests**.
- `mutation.log`: **6/6 mutants killed**, including test-split leakage, wrong selection/tie rules, missing hash/output checks and reuse under a changed scoring plan.
- `check-all.log` and `checks/`: **22/22 PASS**, runtime **2,248 passed, 100 skipped**, backend **287 passed**. The check ran in `.scratch/v3-step2-verify`, detached at `ae96728`. The first targeted run imported perturbation from the wrong module; `targeted-second.log` and `targeted-final.log` show the repair. `test-first.log` records the missing tracker before implementation in a scratch copy.

Commands: `scripts/check-all.sh <fresh checks directory>`; mutation harness as in the runner receipt, with `tests/v3/test_v3_tracker.py` and this folder's `mutants.json` (no worker script needed).

## What this does NOT show

No GPU, Windows, real-model acceptance or evidence that ES learned a task. These are offline tiny-model and deterministic split/selection/export checks. The shared lab still supports declarative scorers only. Audit scheduling, a deployable r11 qualification flow and the v3 flag day remain separate work.
