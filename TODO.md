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

## step6-polish  (`src/heteroes/eval/`, `scripts/run_one_candidate.py`; step 6 itself is done)
- [ ] Clean up the 1660S: `/tmp/heteroes_step7.bundle`, `/tmp/step7/`, `/tmp/step7_pytest.log`, `/tmp/step7_run.log`, the extra local branch `feat/perturb-restore-update` and the detached HEAD (go back to a branch); change the password and use an SSH key.
- [ ] `run_one_candidate.py` records only a yes/no `git_dirty` (the format-2 script still does); recording the list of paths that differ would explain a dirty tree
      (the 2026-10-05 evidence is dirty because of one unrelated untracked notebook).
- [ ] `candidate.py`: `model_weights_sha256` reads every tensor through the CPU (3 times per candidate): 0.6 s each on the 5070 Ti and 4.2 s each on the 1660S (about 12 s of a 40 s run there).
- [ ] Docstrings are short; the `evaluate_model` batch-size assumption (one prompt at a time, no padding) is only a comment.

## learning  (after the first experiment of 06/10; see `artifacts/experiments/2026-10-06-learning-pilot/README.md`)
- [ ] The replication of alpha 1e-3 did not meet S2 (7 of 10): run more seed families (same criteria, written before) before saying that the control confirms the direction.
- [ ] Save the final weights (or a checkpoint) of a run, so that the model that learned can be inspected and evaluated later.
- [ ] sigma = 1e-3 looks strong (candidates are 0.06 to 0.11 below their parent, only 0 to 3 of 8 beat it): try a smaller sigma with the same criteria; also alpha between 1e-3 and 3e-3 and a larger N.
- [ ] A held-out set of another distribution (3-term sums, parentheses) and the frozen 16-question workload before and after: does the gain transfer, or hurt?
- [ ] A baseline of random directions (not only the anti-step) and, later, a comparison with another method.
- [ ] The CPU noise generation (about 2 minutes of the 2.2 minutes per generation) is the cost: parallelize the chunks or generate on demand; the noise is independent per chunk, so this is possible without changing a byte.
- [ ] Put the experiment into the package with tests if it is to be reused (today: experiment scripts in the artifact folder, not tested).

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

## manifest-next  (after step 8; O5 and O6 are decided, see contract sections 3, 10, 12)
- [ ] `engine.derive_chunk_seed` itself does not check the seed type (`"1"` gives the same noise as `1`). Today `apply_es_update_` and
      `CandidateDescriptor` check; consider checking in `ChunkNoiseAddress` too (the engine accepts any integer on purpose: golden vectors).
- [ ] The record of a whole generation (list of descriptors, coefficients, `alpha`, parent weights): with the ledger. `alpha` is deliberately NOT in the recipe.
- [ ] The noise self-test is not part of a worker admission yet (C1): a worker whose fingerprint differs must not receive candidates.
- [ ] Run the format-2 `run_one_candidate.py` on the 1660S too and store the record (needs a new SSH authorization). Done on the 5070 Ti
      (`artifacts/regression/2026-10-06-manifest-v1-5070ti/`); the earlier evidence has format 1 (its recipe hash was checked offline and agrees).
- [ ] `derive_seed` is the coordinator's way of choosing seeds; it is not used by any runtime code yet.
- [ ] Parent weights fingerprint (`parent_weights_sha256`) costs one pass over the model (0.6 s on the 5070 Ti, 4.2 s on the 1660S): check it once per generation.
- [ ] Optional: an inference canary (hash of the 16 base outputs) as a separate admission check, NOT in the recipe (it would change with the inference library).

## ledger-next  (`src/heteroes/ledger/`; G2a to G2d, 06-07/10/2026)
- [ ] Worker ids are free strings: there is no worker registry yet. Quarantine blocks exactly that name, so a worker that renames
      itself escapes it. Acceptable while workers are trusted (no attacker in scope); revisit with C1 admission (worker identity,
      capability profile), where a registry is needed anyway.

## schema-polish  (`src/heteroes/model/schema.py`)
- [ ] The two existing `TODO(...)` comments in the source: `schema-validation` (`__post_init__`) and
      `schema-polish` (docstrings, hints). The `canonical_json_bytes` part is done: `heteroes/canonical.py` (06/10); the comment in `schema.py` still mentions it.

## notebooks
- [ ] `notebooks/floating_point_testing.ipynb` (untracked): the NumPy cell starts from the float64
      `theta`, the torch cells from `theta_float16`. Use `theta_float16` in both before relying on it.
