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
- [x] (done in G6, 07/10) The CPU noise generation is parallel: perturb 3.7 s -> 0.75 s, update of 8 candidates 44.9 s -> 2.4 s on the 5070 Ti, same bits (contract section 14). The learning experiments can be re-run much faster.
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

## ledger-next  (`src/heteroes/ledger/`, `src/heteroes/generation_record.py`; G2a to G2f, 06/10/2026; design in ADR-002 and its amendments of G6)
- [ ] Worker ids are free strings: there is no worker registry yet. Quarantine blocks exactly that name, so a worker that renames
      itself escapes it. Acceptable while workers are trusted (no attacker in scope); revisit with C1 admission (worker identity,
      capability profile), where a registry is needed anyway.
- [ ] `CandidateState.RUNNING` exists (it is in the table's `CHECK`) but nothing produces it and `lease`, `submit_result` and `report_failure` treat it as "not leasable / closed": a heartbeat did not need it (G6), so either handle it like LEASED or remove it.
- [ ] No schema migration (a file of another version is refused; the version is 5). `max_attempts` is a policy of the process, not stored: two
      processes with different values disagree about FAILED.
- [ ] An expired lease is not written down (`ended_at` and `failure_kind` stay NULL), so the ledger cannot say afterwards that an attempt timed out; `release_worker` deletes the quarantine row, so the history of a quarantine is lost (the events log has it).
- [ ] `generation_record.py` imports private helpers of `manifest.py` (`_HEX64`, `_NAME`, `_check_int`, `_check_keys`, `_check_text`): make
      them public or move them to a shared module (touches the frozen manifest, with its tests as a guard).
- [ ] The ledger tests import torch because the model of the contract (`tests/ledger/harness.py`) and `GenerationRecord.from_results` use
      `standardize_rewards`, which lives in `es/update.py`. Moving it to a module without torch would keep the ledger free of torch.
- [ ] `GenerationResults` has no `experiment_id` / `generation` fields, so `GenerationRecord.from_results` takes them as arguments.
- [ ] `ledger/ledger.py` is one file of about 900 lines: leases, results, generation state, quarantine and the update record could be split.
- [ ] The tests of the ledger take about 27 s by default (the exhaustive worlds are about 25 s of it); the deep mode takes 88 s. The model of the contract (`harness.py`) knows the charged attempts and the late quarantine of G6 but not `extend_lease` and the chain (those have their own tests in `test_hardening.py`).
- [ ] The mutation checks were made by hand with scripts in the scratchpad of the session (lists of faults), which are not in the repo
      and are lost when the scratchpad is cleaned; only the counts are recorded (STATUS 0.0, 0.000). A reusable runner would need an agreed list of faults per module.
- [ ] ADR-002 is a draft by Claude pending the owner's review; its amendments of G6 (the owner has not reviewed them either).

## g3-next  (HTTP worker and coordinator; G3, 06/10/2026; reviewed after the audit of 07/10)
- [x] (G6) Restart procedure of the coordinator, heartbeat, repeatable lease requests, an outbox for undelivered rewards, resumable downloads, a socket timeout and a connection limit, a token required off loopback, pruning of the published weights, aborted vs finished: see ADR-002 amendments and `scripts/failure_campaign.py`.
- [ ] The token is sent in clear over HTTP (acceptable on a private cable or Tailscale; do not expose the port). No TLS, no per-worker identity.
- [ ] The network set-up of the two machines (`eno1` addresses `10.10.10.1/24` and `10.10.10.2/24`, the ufw rule for 8765/tcp on `eno1`) was made
      by hand and is not in the repository; write it in a short runbook (or a checked script) if the demo must be repeated.
- [ ] A worker that never gets its candidate to the coordinator through a coordinator restart inside one lease keeps the reward in its outbox only while its process lives; a worker that dies loses it (the lease then runs out and another worker redoes it).
- [ ] `tests/test_e2e_local.py` takes about 5 minutes and three processes on the GPU: it runs only with `HETEROES_E2E=1`.
- [ ] The mutation check of G3 and of G6 (see STATUS 0.000 for the counts) was made with scripts in the scratchpad, not in the repo.
- [ ] A load that fails halfway (`load_weights_`, disk error) leaves the model half loaded; the worker raises and dies, which is the safe outcome, but no test kills a worker there.

## schema-polish  (`src/heteroes/model/schema.py`)
- [ ] The two existing `TODO(...)` comments in the source: `schema-validation` (`__post_init__`) and
      `schema-polish` (docstrings, hints). The `canonical_json_bytes` part is done: `heteroes/canonical.py` (06/10); the comment in `schema.py` still mentions it.

## notebooks
- [ ] `notebooks/floating_point_testing.ipynb` (untracked): the NumPy cell starts from the float64
      `theta`, the torch cells from `theta_float16`. Use `theta_float16` in both before relying on it.

## c1-next  (G4/G5, 07/10/2026; updated after G6)
- [ ] Decide the evaluation precision (numerical contract section 15): the FP32 forward pass removed every padded-batch difference and (see STATUS 0.000 for the two-GPU result) is 5 times faster at chunk 16 than the FP16 reference path; it needs the owner's decision because it changes every reward (a new recipe hash) and costs 2 GB of GPU memory more.
- [ ] The prediction of the admission is fitted on the profile (`fit_affine`, residuals in the profile) and not on the benchmark runs; it still ignores the polling delay of the workers (up to 1 s per generation), the variation between candidates and the CPU shared by the coordinator and the local worker.
- [ ] `profile_worker.py` blocks the SSH session when started with `ssh ... &` without `setsid nohup ... < /dev/null`: always use the latter (the cluster runner does).
- [ ] B1 and B2 do not steal and do not reassign: with a dead worker they now stop on the stall rule of the coordinator instead of waiting for ever (a baseline, on purpose).
- [ ] The 1660S profile and the synchronization were measured over the direct cable only (no Tailscale/Wi-Fi comparison).
- [ ] A workload whose rollout is long (more prompts, longer answers, a task that needs reasoning) would let a slow GPU matter more: today the 16 prompts of the smoke workload take 0.16 to 0.8 s on the fast GPU, so the CPU noise and the update dominate.
- [ ] The cross-GPU sweep is 120 candidates per setting: it estimates a rate of about 1 percent only roughly; the benchmark runs themselves can serve as a larger sample (every candidate evaluated on the 1660S is compared with the reference).
