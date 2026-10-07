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
- [ ] `apply_coefficients_` / `_check_coefficients` (06/10) have only short comments and long signature lines, in the style of the rest of the file; the docstring of `apply_coefficients_` should also say what it does NOT guarantee (a runtime failure while writing leaves the model half updated; restore from the snapshot), as for `apply_es_update_` below.
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
- [ ] The noise self-test is not part of a worker admission yet (C1): a worker whose fingerprint differs must not receive candidates.
- [ ] Run the format-2 `run_one_candidate.py` on the 1660S too and store the record (needs a new SSH authorization). Done on the 5070 Ti
      (`artifacts/regression/2026-10-06-manifest-v1-5070ti/`); the earlier evidence has format 1 (its recipe hash was checked offline and agrees).
- [ ] `derive_seed` is the coordinator's way of choosing seeds; it is not used by any runtime code yet.
- [ ] Parent weights fingerprint (`parent_weights_sha256`) costs one pass over the model (0.6 s on the 5070 Ti, 4.2 s on the 1660S): check it once per generation.
- [ ] Optional: an inference canary (hash of the 16 base outputs) as a separate admission check, NOT in the recipe (it would change with the inference library).

## ledger-next  (`src/heteroes/ledger/`, `src/heteroes/generation_record.py`; G2a to G2f, 06/10/2026; design in ADR-002)
- [ ] Worker ids are free strings: there is no worker registry yet. Quarantine blocks exactly that name, so a worker that renames
      itself escapes it. Acceptable while workers are trusted (no attacker in scope); revisit with C1 admission (worker identity,
      capability profile), where a registry is needed anyway.
- [ ] The restart procedure of the coordinator (SUPPORTING in MASTER): compare the hash of the weights with `parent` and `child` of the stored
      update record, restore from the parent checkpoint if needed, redo the (deterministic) update, `mark_applied`. Only the data (the record,
      `mark_applied`) exists; checkpoint staging and publication do not.
- [ ] The chain `parent_weights_sha256` of generation g+1 = `child_weights_sha256` of generation g is not enforced by `open_generation` (all the
      tests use one parent for every generation, so enforcing it means changing fixtures). Decide with the owner.
- [ ] `CandidateState.RUNNING` exists but nothing produces it (a worker telling "I started" and heartbeats come with the HTTP protocol).
- [ ] No schema migration (a file of another version is refused; the version is 5). `max_attempts` is a policy of the process, not stored: two
      processes with different values disagree about FAILED.
- [ ] `generation_record.py` imports private helpers of `manifest.py` (`_HEX64`, `_NAME`, `_check_int`, `_check_keys`, `_check_text`): make
      them public or move them to a shared module (touches the frozen manifest, with its tests as a guard).
- [ ] The ledger tests import torch because the model of the contract (`tests/ledger/harness.py`) and `GenerationRecord.from_results` use
      `standardize_rewards`, which lives in `es/update.py`. Moving it to a module without torch would keep the ledger free of torch.
- [ ] `GenerationResults` has no `experiment_id` / `generation` fields, so `GenerationRecord.from_results` takes them as arguments.
- [ ] `ledger/ledger.py` is one file of about 700 lines: leases, results, generation state, quarantine and the update record could be
      split when the HTTP code arrives.
- [ ] The tests of the ledger take about 27 s by default (the exhaustive worlds are about 25 s of it); the deep mode takes 88 s. Mark them or shrink
      the worlds if the suite gets in the way.
- [ ] The mutation checks of G2a to G2f were made by hand with scripts in the scratchpad of the session (lists of faults), which are not in the repo
      and are lost when the scratchpad is cleaned; only the counts are recorded (STATUS 0.0). Keep the lists if they are to be reused.
- [ ] ADR-002 is a draft by Claude pending the owner's review; the worker protocol table in it is a proposal [P], not implemented.

## g3-next  (HTTP worker and coordinator; G3, 06/10/2026)
- [ ] Failures on the physical machines are not exercised: kill a worker in the middle of a candidate, cut the cable during a download,
      let a lease expire on the 1660S (the behaviour is tested with fake workers and in the simulations only). This is the C3 campaign (E6).
- [ ] The restart procedure of the coordinator is still not written (see `ledger-next`).
- [ ] Nothing produces `CandidateState.RUNNING`; the worker sends no heartbeat, a long candidate on a slow worker is only protected by the lease length.
- [ ] The token is sent in clear over HTTP (acceptable on a private cable or Tailscale; do not expose the port). No TLS, no per-worker identity.
- [ ] The network set-up of the two machines (`eno1` addresses `10.10.10.1/24` and `10.10.10.2/24`, the ufw rule for 8765/tcp on `eno1`) was made
      by hand and is not in the repository; write it in a short runbook if the demo must be repeated.
- [ ] Published weights (about 1 GB per generation) are never deleted by the coordinator (8 GB in `~/.cache/heteroes` after the G3 runs).
- [ ] The first physical runs give no speedup (the coordinator's update is about 46 s per generation for 8 candidates; the 1660S is about 4 times
      slower per candidate): profile the update and the synchronization before any claim (C2, C4). One run per configuration only.
- [ ] `tests/test_e2e_local.py` takes about 5 minutes and three processes on the GPU: it runs only with `HETEROES_E2E=1`.
- [ ] The mutation check of G3 (70 random operator mutants of `coordinator`, `worker`, `worker_runtime`, `worker_api`, `http_transport`, `executor`,
      `dispatch`: 61 caught, 7 equivalent, 2 gaps closed by three new test cases) was a sample made with a script in the scratchpad, not in the repo.

## schema-polish  (`src/heteroes/model/schema.py`)
- [ ] The two existing `TODO(...)` comments in the source: `schema-validation` (`__post_init__`) and
      `schema-polish` (docstrings, hints). The `canonical_json_bytes` part is done: `heteroes/canonical.py` (06/10); the comment in `schema.py` still mentions it.

## notebooks
- [ ] `notebooks/floating_point_testing.ipynb` (untracked): the NumPy cell starts from the float64
      `theta`, the torch cells from `theta_float16`. Use `theta_float16` in both before relying on it.

## c1-next  (G4/G5, 07/10/2026)
- [ ] Decide what to do about the cross-GPU difference of a reward (1 candidate in 24 differed by one question between the 5070 Ti and the 1660S at chunk 1 in a reference run, 1 more in a G4 run, none in 264 evaluations of G5; see
      `artifacts/experiments/2026-10-07-g4-admission-b2/README.md`): hardware noise accepted and reported, one GPU model per experiment, or find the layer that differs.
      The G3 README says "bit-identical" for 24 candidates; that sentence needs the caveat.
- [ ] `chunk > 1` is not exact in FP16 with left padding on either GPU (every chunk above 1 changed some answer text over 33 states). A different batching that keeps
      the numbers (same padded length for every call, or sorting by length) is not tried; until then the per-worker chunk of C1 is 1 everywhere and sizing has nothing to size.
- [ ] The prediction has one fixed update term calibrated on the G4 runs (10.2 s, two points) and a candidate time that is the median of 5; it ignores the polling delay,
      the variation between candidates and the CPU shared by the coordinator and the local worker. Over-prediction of 13 to 19 percent in G4.
- [ ] `profile_worker.py` blocks the SSH session when started with `ssh ... &` without `setsid nohup ... < /dev/null`: always use the latter (see how `run_benchmark.py` does it).
- [ ] B2 has no stealing and no re-assignment if its worker dies (a baseline; a failed candidate returns to the same worker). A B2 run with a dead worker waits for the retry budget.
- [ ] The 1660S profile and the synchronization were measured over the direct cable only (no Tailscale/Wi-Fi comparison).
