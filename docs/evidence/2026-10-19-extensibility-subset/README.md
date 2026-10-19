# Extensibility — subset weight spaces (trainable schema)

Baseline: `595a1b4` (step 1 receipts), branch `feat/extensibility-step0`. Implements the subset part of ADR-008 section 4
(draft) in `runtime/src/heteroes/model/schema.py`, which is not one of the frozen numerical modules. `noise/`, `es/`,
`ledger/` and `generation_record.py` are unchanged; nothing in the product builds a subset yet.

## What changed

- `select_parameters(full_schema, include)` returns a trainable schema with version `heteroes.parameter_schema.v1.subset`:
  the full schema's entries whose canonical name or an alias matches a pattern (`re.search`), unchanged (original index
  included) and in order. A tied tensor is selected when any of its names matches; a subset of a subset is refused.
- `resolve_tensors` accepts a subset schema only as an ordered selection of the model's own entries; a full schema must
  still match the model exactly, as before (the existing mismatch tests are unchanged and pass).
- ADR-008 section 4 now states this rule.

## What the tests show (`runtime/tests/model/test_subset_schema.py`)

- The unchanged `perturb_model_`, `take_snapshot`/`restore_from_snapshot_` and `apply_coefficients_` move exactly the
  selected tensors; every other tensor stays bit-identical; restore is exact.
- The noise of a subset tensor is the FP32 rule at address (seed, subset hash, original index).
- A full schema still refuses a model with an extra parameter. A subset accepts a model with an extra module registered
  last (the subset does not pin what it leaves out — in v3 the pinned model files do) but refuses a model whose parameter
  indices moved, a reordered, reshaped, renumbered or empty subset.

## Receipts

| Check | Result | File |
| --- | --- | --- |
| Full CPU product check | 22/22 PASS; runtime 2,168 passed (12 new), 100 skipped; backend 287 passed | `check-all.log`, `checks/` |
| Mutation check, first run | control passes; 7/8 killed (`re.match` instead of `re.search` survived) | `subset-mutants.json`, `subset-mutation.log` |
| Mutation check, after one new test (pattern in the middle of a name) | control passes; 8/8 killed | `subset-mutation-final.log` |

## What this does NOT show

No real model (Qwen) subset, no GPU or CUDA-engine run (`perturb_model_cuda_` with a subset is not tested), no LoRA, and no
learning result for subsets. The worker does not yet build a trainable schema from a recipe.
