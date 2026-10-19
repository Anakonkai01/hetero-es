# Recipe v3 product runner and worker — CPU integration

Source checkpoint: `c9eccfd`, on `feat/v3-product-integration`, based on `a804eac`.

- Managed coordinator and the shipped `scripts/run_worker.py` run two generations over authenticated loopback HTTP with an offline tiny Qwen2 model, for full, subset and LoRA spaces. Workers submit texts; re-scoring the ledger texts reproduces every committed reward. Signs and version-2 update records are checked.
- Product configuration builds the same documents as the SDK, rejects Python scorers, checks dataset/model/schema identities and freezes recipe/plan files. Agent preparation retains arbitrary dataset columns and supplies the worker's frozen configuration.
- LoRA workers fetch the pinned initial adapter over the existing authenticated private weights transport. It remains available after old weights are pruned. Restart, changed-plan and corrupted-adapter tests are included.
- `targeted-repaired.log`: 39 passed. `mutation.log`: control passes, **6/6 mutants killed**, no equivalences.
- `check-all-final.log` and `checks-final/`: **22/22 PASS**, runtime **2,241 passed, 100 skipped**, backend **287 passed**. This final check ran in the detached checkout `.scratch/v3-step1-verify` at `c9eccfd`, with the existing Python environment and hard-linked Node dependencies. The main working branch could then advance independently.

Intermediate receipts are retained: the first targeted run used the not-yet-supported `centered-rank@1`; the tests were corrected to the supported `zscore@1`. The first full check found missing imports in the new agent test (runtime and Ruff); `agent-final.log` and the final full check show the repair. `targeted-final.log` is an intermediate failed receipt; `targeted-repaired.log` supersedes it.

Commands: `scripts/check-all.sh <fresh checks directory>`; `scripts/mutation-check.py --repo runtime --copy src --copy scripts/run_worker.py --copy tests --copy artifacts/probes --copy artifacts/regression --copy artifacts/experiments/2026-10-09-chunk128 --env PYTHONPATH=src --env CUDA_VISIBLE_DEVICES= --test '<heteroes-match python> -m pytest -q -p no:cacheprovider tests/v3/test_v3_product.py' --mutants <this folder>/mutants.json`.

## What this does NOT show

No GPU work, real Qwen checkpoint acceptance, learning result, Windows qualification, r11 packaging, live-lab operation or deployment. The fixture's declarative rewards can all be zero; completing generations is protocol evidence, not a learning claim. Cold LoRA workers need a private route to fetch their initial adapter; a public replay-only route can reuse an already verified cache. Audit scheduling and the flag day remain later work. Protected numerical/protocol files and historical artifacts are unchanged.
