# FP32 generation with a selective CPU reference — diagnostic only

The owner questioned the practicality of full FP64 generation on consumer GPUs. The earlier full-reference
probe remains diagnostic evidence, not an approved product decoder. This follow-up measures a scratch-only
alternative on the same failing g10/c5 candidate: keep GPU generation FP32, and recompute only rows whose
top-two processed scores differ by less than 0.01, using a CPU reference. No installed runtime changes.

Inputs and independently reconstructed parent proof are preserved in
[the original investigation](../2026-10-20-audit-mismatch-investigation/RESULTS.md).
The cached parent is SHA256-verified before use. Every candidate restores the original parent exactly.

`scripts/test_margin_guard.py` was run before implementing the scratch helper: collection failed because the
helper did not exist. Two focused tests then passed; all four scratch mutations were killed. These tests check
row/prefix selection and score replacement, not a numerical error bound. Scripts and original logs are preserved.

## What this does NOT show

No universal error bound or cross-hardware guarantee, no large-model cost claim, no 50-generation acceptance,
no Windows test and no production fix. A threshold gate can itself disagree across devices near its boundary.
All times are single ordered measurements; the control runs first and the guarded run may benefit from warmup.
No speedup or percentage-overhead conclusion is justified. No product source, installer or live lab changed.

The owner's concern is not approval for a new decoder. The near-tie policy decision remains pending under
numerical-contract section 17; old `hf_generate` recipe meanings and strict audit equality remain unchanged.
