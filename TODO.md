# TODO — code-level debt

Small, concrete clean-up items. Not a roadmap (see `HETEROES_LLM_MASTER.md`) and not a status report
(see `HETEROES_LLM_STATUS.md`). When an item is done, delete it.

## snapshot-polish  (`src/heteroes/es/snapshot.py`)
- [ ] Docstrings for `take_snapshot`, `diff_from_snapshot`, `restore_from_snapshot_`. State that after a
      `RestoreError` the model state is undefined and the worker must be quarantined.
- [ ] `es/checks.py` exports underscore-prefixed names (`_check_param`, `_check_sigma`,
      `_check_param_sigma`) that other modules import; rename them without the underscore.
- [ ] Merge the two `from heteroes.model.schema import ...` lines.
- [ ] Fix inaccurate comments ("copy a tensor from gpu to cpu", "check contiguous"), the typo
      "reinterpretate", the vague "avoid Nan or complement"; resolve or delete both TODOs
      (non-blocking; do we check contiguity of a hand-built `Snapshot`).
- [ ] Type hints (`slab_elements: int` in `diff_from_snapshot`); rename `DEFAULT_SLAB` to
      `DEFAULT_SLAB_ELEMENTS`; drop the unused `entry` in the restore loop; trailing whitespace.
- [ ] `RestoreError` message: "Restore left N tensor(s) different from the snapshot: [...]".

## perturb-polish  (`src/heteroes/es/perturb.py`)
- [ ] Docstring for `perturb_model_` (all-or-nothing, and its limit: a runtime failure such as CUDA OOM
      still leaves the model half perturbed, hence restore).
- [ ] The comment above `sigma_float_32` should say WHY (PyTorch already rounds the scalar to float32;
      the line is kept so we do not depend on that).
- [ ] `resolve_tensors` error message (`schema.py`): include the ACTUAL canonical name of the first
      differing entry.
- [ ] `perturb.py`: unused `import math` since the checks moved to `checks.py`; trailing whitespace.

## update-wip  (`src/heteroes/es/update.py`, unfinished, step 5)
The tests `tests/es/test_standardize.py` and `tests/es/test_update.py` are the specification and are red until
this is done. Formula: `docs/numerical-contract.md` section 8. Problems of the current draft:
- [ ] Syntax error: `ParameterNoiseAddress(candidate_seed=` is cut off, and the loop over chunks and candidates
      is missing.
- [ ] `DEFAULT_ETA = 1e-9` must be `1e-8` (contract section 7); `DEFAULT_CHUNK_ELEMENTS` is redefined instead of
      imported from `heteroes.noise.contracts`; `resolve_tensors` should come from `heteroes.model.schema`;
      remove unused imports.
- [ ] No-op test is inverted: `if np.all(z_rewards != 0)` returns "noop" for real signal. It must be
      `if not z_rewards.any()`.
- [ ] `UpdateReport` only has `noop`; the tests expect `noop`, `coefficients`, `requested_l2`, `applied_l2`,
      `changed`, `numel`.
- [ ] `standardize_rewards`: reject non-finite rewards, empty input and anything that is not 1-D
      (`ValueError`); `eta` must be positive and finite (the draft only rejects infinity).
- [ ] `apply_es_update_`: validate everything before the first write: schema, every tensor, lengths of seeds and
      rewards, duplicate seeds, finite `alpha`, `eta`; then accumulate in FP32 per chunk, candidate loop innermost,
      multiply and add as separate operations, cast to FP16 once, wrap the writes in `torch.no_grad()`.

## schema-polish  (`src/heteroes/model/schema.py`)
- [ ] The two existing `TODO(...)` comments in the source: `schema-validation` (`__post_init__`) and
      `schema-polish` (`canonical_json_bytes`, docstrings, hints).

## notebooks
- [ ] `notebooks/floating_point_testing.ipynb` (untracked): the NumPy cell starts from the float64
      `theta`, the torch cells from `theta_float16`. Use `theta_float16` in both before relying on it.
