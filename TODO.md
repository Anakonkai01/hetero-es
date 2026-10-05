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

## update-polish  (`src/heteroes/es/update.py`; step 5 itself is done, 05/10 evening)
- [ ] Docstrings for `UpdateReport`, `standardize_rewards` and `apply_es_update_`. State what `apply_es_update_` does NOT
      guarantee: a runtime failure while writing (for example CUDA out of memory) leaves the model half updated, so the
      caller must restore from the snapshot (same limit as `perturb_model_`).
- [ ] Comments and style: the comment `# agentic esopt update style`, trailing whitespace, the `# compare` stub, the
      messages of the errors (typos like "lenght"), type hints (`candidate_seeds: Sequence[int]`).
- [ ] The fields of `UpdateReport` are not formally approved (they come from what `test_update.py` expects).
- [ ] Not run on the 1660S (CPU and GPU agree on the 5070 Ti only).

## step6-polish  (`src/heteroes/eval/`, `scripts/run_one_candidate.py`; step 6 itself is done)
- [ ] A small comparison script for two JSON records (needed by step 7): equal hashes, equal predictions, a readable list of differences.
- [ ] `run_one_candidate.py` records only a yes/no `git_dirty`; recording the list of paths that differ would explain a dirty tree
      (the 2026-10-05 evidence is dirty because of one unrelated untracked notebook).
- [ ] `candidate.py`: `model_weights_sha256` reads every tensor through the CPU (3 times per candidate, about 0.6 s each on the 5070 Ti); measure it on the 1660S.
- [ ] `canonical_json_hash` in `workload.py` repeats the serialization of the schema hash (see `schema-polish`): keep ONE.
- [ ] Docstrings are short; the `evaluate_model` batch-size assumption (one prompt at a time, no padding) is only a comment.
- [ ] Not run on the 1660S.

## dedupe  (idea raised 05/10, nothing decided; touching verified code needs approval)
- [ ] Chunk geometry (`start = chunk_index * chunk_elements`, `chunk_length`) is computed in `engine.iter_parameter_noise_chunks`
      and would be computed again in `update.py`. Options: (1) use `num_chunks` / `chunk_length` in update and keep one
      multiplication; (2) add a small helper to the engine that yields `(chunk_index, start, n)` and use it in both places
      (refactor of verified code, `tests/noise/test_engine.py` would guard it).
- [ ] The prelude `resolve_tensors` + `_check_param` for every tensor is repeated in `take_snapshot`,
      `diff_from_snapshot`, `restore_from_snapshot_`, `perturb_model_` and `apply_es_update_`: candidate for one helper.
- [ ] `schema.hash` + `ParameterNoiseAddress(...)` is built in `perturb_model_` and in update (only twice: leave for now).

## monitoring  (future; not needed for the step 5-9 gate)
Rounding errors that decision O4 = A accepts (contract section 8). Today they are measured once by scratch
scripts that are not in the repo; the goal is to make them visible later for debugging, monitoring and comparison
with other methods (for example the realized difference as the update direction).
- [ ] Put the two measurements of section 8 into a reusable script or function under `scripts/` (with a test on a toy
      model), so they can be re-run for other sigma, other seeds and ES-modified weights.
- [ ] Add optional diagnostics to the update report: cosine and relative L2 error between the canonical epsilon and
      the realized perturbation `(theta' - theta) / sigma`, and the fraction of unchanged elements after perturb.
      The extra pass costs time and memory (the realized perturbation needs theta before and after), so it must be opt-in.
- [ ] Log these numbers per generation in the run artifacts (manifest / events) once those exist.
- [ ] Open question: does the rounding of theta' bias learning (effect on reward or on the aggregated update direction)?
      Not measured. Needs a real ES run before any claim.
- [ ] Investigate the maximum element-wise relative error 0.747 of the FP16 cast of epsilon (suspected: very small |epsilon|).
- [ ] Compare with option B (realized difference as the direction) only if monitoring shows the error growing, for
      example at small sigma or after many generations.

## seeds  (decide at step 8, manifest freeze)
- [ ] O5: where candidate seeds come from (explicit list vs derived from experiment, generation, candidate index).
- [ ] Seed range: the engine accepts any integer; JSON read by JavaScript keeps integers exactly only up to 2^53.
      Restrict the range or write seeds as strings in the manifest (also a question for the engine contract).
- [ ] `engine.derive_chunk_seed` itself does not check the seed type (`"1"` gives the same noise as `1`).
      Today only `apply_es_update_` checks; consider checking in `ChunkNoiseAddress` too.

## schema-polish  (`src/heteroes/model/schema.py`)
- [ ] The two existing `TODO(...)` comments in the source: `schema-validation` (`__post_init__`) and
      `schema-polish` (`canonical_json_bytes`, docstrings, hints).

## notebooks
- [ ] `notebooks/floating_point_testing.ipynb` (untracked): the NumPy cell starts from the float64
      `theta`, the torch cells from `theta_float16`. Use `theta_float16` in both before relying on it.
