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

## g7-next  (G7, 07/10/2026: CUDA noise engine, long workload; the work is in the working tree, uncommitted and unreviewed)
- [x] (done 07/10, G7) The CUDA noise engine and the long workload are choices of the recipe (the CPU engine stays the default, v1 hashes unchanged); executor, coordinator, `build_recipe`, the worker, the scripts and the end-to-end test use them. Left over: the update record does not say which engine made it (the recipe hash does, and the ledger stores it).
- [ ] A coordinator without a CUDA GPU cannot reconstruct this noise (no CPU reference): decide whether the engine is for runs whose coordinator has a GPU only, or write a CPU reference of curand's generator (hard) or choose S2 (an integer counter-based generator with a table, portable by construction, with a NumPy reference).
- [x] (done 07/10) The self-test runs on every worker (`run_worker.py`) and on the coordinator (`run_coordinator.py`, `reference_generations.py`) for a CUDA recipe. Left over: the torch and CUDA versions are in the environment event of each process but not checked against each other at admission; a GPU with fewer than 88 blocks of the random kernel (a GTX 1650 and smaller) is refused by `check_device` at the call size of 22,528 (a smaller call is possible but costs launches).
- [ ] Re-run the evidence (`cuda_engine_crossgpu.py` on both machines) after every torch or CUDA upgrade; only two GPUs and one software stack were compared.
- [x] (done 07/10) The real cluster with the long workload, both engines, 3 runs per cell: `artifacts/experiments/2026-10-07-g7-cluster-benchmark/`. Left over: N = 24 only (try 48 and 96, where the estimate says the 1660S adds more), more runs per cell, a profile of the long workload made by `profile_worker.py` (it still profiles the 16-prompt workload with the CPU engine; the benchmark used medians of the restore trade-off experiment as the starting speeds).
- [ ] The effect of the drift of the arithmetic way back on learning was not measured (only that it grows like sqrt(k)): decide whether to test it, or keep the snapshot restore (3 percent of a candidate of the long workload) and stop.
- [ ] Reduce the launch overhead further (CUDA graphs of the call sequence of a tensor) if the 0.08 s of a perturbation on the 5070 Ti and the 0.58 s on the 1660S matter; the 0.58 s is the launch cost on a slow CPU.
- [ ] `restore_tradeoff.py` was run once per arm with 24 candidates; more candidates or repeats would give intervals. The rollout time depends on the candidate, so compare the phases outside the rollout, not the totals.

- [x] (done 07/10) A bigger chunk for the long workload: exactness probe on both GPUs and a benchmark with chunk 32 and 64 (`artifacts/experiments/2026-10-07-g7-bigchunk/`). Left over: a chunk per worker (the 1660S gains more from a big chunk; the code has `per_worker_chunk` for the safe chunk of a profile, not used here); chunks above 64 (needs a workload with more questions); the probe for another model or workload; `profile_worker.py` does not know the long workload, so the safe chunk was probed by `chunk_probe_cot.py` instead.
- [ ] The second worker process on the 5070 Ti gives nothing for the long workload (one process 107.6 s, two 108.5 s): use one process in the next benchmarks of this workload, and keep B0x2 only where the CPU noise is still large (the CPU engine, the 16-prompt workload).

## c1-next  (G4/G5, 07/10/2026; updated after G6)
- [x] (done 07/10, O8) FP32 is the default evaluation precision, chunk 16 the default chunk. Left over: the profiles and benchmark plans of G4/G5 are FP16 (their READMEs say so); the plan of `run_benchmark.py` still looks up a profile by chunk, so a new FP32 profile is needed to use it with the defaults.
- [ ] The prediction of the admission is fitted on the profile (`fit_affine`, residuals in the profile) and not on the benchmark runs; it still ignores the polling delay of the workers (up to 1 s per generation), the variation between candidates and the CPU shared by the coordinator and the local worker.
- [ ] `profile_worker.py` blocks the SSH session when started with `ssh ... &` without `setsid nohup ... < /dev/null`: always use the latter (the cluster runner does).
- [ ] B1 and B2 do not steal and do not reassign: with a dead worker they now stop on the stall rule of the coordinator instead of waiting for ever (a baseline, on purpose).
- [ ] The 1660S profile and the synchronization were measured over the direct cable only (no Tailscale/Wi-Fi comparison).
- [ ] A workload whose rollout is long (more prompts, longer answers, a task that needs reasoning) would let a slow GPU matter more: today the 16 prompts of the smoke workload take 0.16 to 0.8 s on the fast GPU, so the CPU noise and the update dominate.
- [ ] The cross-GPU sweep is 120 candidates per setting: it estimates a rate of about 1 percent only roughly; the benchmark runs themselves can serve as a larger sample (every candidate evaluated on the 1660S is compared with the reference).
- [ ] (idea, not built, the numbers are inferences) A compressed delta synchronization: the update changes about 98 percent of the FP16 elements but by a few units of the last bits, so the XOR of the new and the old bit patterns, split into its high and low bytes and compressed (zstd), might be about a third of the 1 GB; the transfer (8.5 s of the 10 s synchronization of the 1660S) would then be about 3 s, at the price of a decompression on its slow CPU. Worth measuring only if a configuration is found in which the 1660S's time per generation, not its candidate speed, is the limit.
- [ ] The 1660S candidate (FP32, chunk 16: 4.9 s) is 3.3 s of CPU noise on a 2012 Xeon (16 threads) and 1.6 s of GPU: its CPU, not its GPU, is the limit. The noise cannot be moved to another machine without shipping the weights (replay loses from N = 3, see the profiles README).

## learning-runtime-next  (the learning experiment of the night of 07/10 to 08/10; nothing here is decided, the owner chooses)
- [ ] Held-out level 2 (H2) wanders by 15 to 30 questions between neighbouring checkpoints late in the run: a larger H2 set, or the average over the last checkpoints, before S4 is read again.
- [ ] `scripts/cluster_runner.py: collect_and_clean` copies the worker log of the 1660S only at the end: when the machine is down the log is lost (both runs of the night); copy it periodically, or let the worker send its events to the coordinator.
- [ ] The 1660S went down twice in 6 hours under load. The owner says it is a GPU/PCIe fault (maybe a loose contact), cured by a restart and back after some hours: look at `journalctl -b -1` (may need sudo) and re-seat the card before the next two-machine campaign; until then use the 5070 Ti alone for long runs.
- [ ] `run_learning.py` and `analyze_run.py` have no unit tests (only the helpers in `learnlib.py` do); (the full `pytest tests` was re-run on the 5070 Ti after the changes: 1994 passed, 4 skipped; not on the 1660S).
- [ ] Replay is a probe script (`artifacts/experiments/2026-10-08-c4-replay/replay_probe.py`), not a path of the worker: a worker that is behind could replay (N below about 19, or a link below about 720 Mbit/s) instead of downloading 988 MB; the choice rule would use the measured seconds per candidate of the worker. Not built.
- [ ] `THIRD_PARTY` file and the ownership / AI-use statement (MASTER section 16) are not written; the report draft (`docs/report/REPORT.md`) says so.
- [ ] (learning, after the second experiment of 08/10) Run D1 moved the model to answering directly (the base asked for only the integer scores 77.0 percent on H1) and damaged the word problems (H3 81 -> 64): train on a MIX of families (levels 1, 2 and 3 in one workload) so that answering directly cannot pay on all of them, and report each family; or give the model the direct mode in the prompt so that the training can only add arithmetic.
- [ ] (learning) D1 and D2 are single runs: replicate D1 with another experiment id (the first experiment's runs differed a lot) before quoting its numbers; D2 changed sigma and alpha together.
- [ ] (learning) Held-out evaluation also at 512 tokens for level 3 hides nothing, but the coordinator still scores training questions with the 256-token limit; a workload with a larger `max_new_tokens` would be a new workload name and recipe hash.

## to-90  (release name: **v0.5.0**, agreed 08/10: feature-complete, NOT reviewed by the owner; then v0.9.0-rc1 after the owner's fixes, v1.0.0 after the big review; tag and `pyproject.toml` version only at the end of the day, nothing pushed) (the way to above 90 percent, from STATUS "RESUME HERE" of 08/10; the owner decides the order)
- [ ] Report: claims audit against MASTER section 12 (each EQ: evidence or `NOT_RUN`), `THIRD_PARTY`, ownership / AI-use statement (needs the owner), every number re-checked against its file (`docs/report/REPORT.md`).
- [ ] C1: make `scripts/profile_worker.py` profile the CUDA engine and the long / level-1 workload on both machines, then repeat the admission prediction against forced admission.
- [ ] Replay as an option of the worker (profile-based rule, optional early start when the record is written, hash check every k generations), two-machine run with both modes and equal final hashes.
- [x] ~~Learning: replicate D1 / mixed-level training~~ DROPPED by the owner on 08/10: the project claims a correct, reproducible, fault-tolerant RUNTIME, not that ES learns (the ES papers did that); the report keeps its honest limits and cites prior art. Moved to `after-v1`.
- [x] ~~GRPO supporting baseline~~ DROPPED by the owner on 09/10: not needed; out of scope for every release (EQ5 is not claimed, MASTER section 14 does not apply).
- [ ] Failure campaign: each scenario 3 times; coordinator kill between the write-ahead record and the update on the real machines.
- [ ] After the 1660S is stable: bundle sync, full tests there, one two-machine benchmark; N = 48 and 96, a chunk per worker.

## after-v1  (said by the owner on 08/10; not before the review)
- [ ] Reproduce a few experiments of the ES papers (ES-at-Scale, Understanding ES, Agentic ESOpt) on this runtime, to add evidence about the SYSTEM (it runs the algorithm correctly at their settings), not to prove that ES works. Use the right baselines: the base model scores 81.2 percent on the level-3 held-out set at 512 tokens (32.8 at 256), and 77.0 percent on level 1 when asked only for the integer (`artifacts/experiments/2026-10-08-uncut-probe`, `-direct-answer-probe`); a gain over the wrong baseline is mostly answering style.
- [ ] Check the papers' numbers quoted in `docs/report/REPORT.md` section 10 against the papers themselves (the AI copied them from MASTER section 3 and has not reopened the papers).

## ideas-remote-workers  (idea of the owner, 08/10: borrow friends' PCs/laptops that stay in their homes; deploy fast, no OS reinstall, Windows stays Windows)
- [ ] A pinned environment for a worker (lock file with the exact torch / transformers / NumPy versions; `pyproject.toml` lists none today) and a one-command `bootstrap_worker` (venv, model download at the pinned revision with hash check, noise / CUDA / restore self-tests, PASS or FAIL report, then join). A "join code" = coordinator address + token in one string.
- [ ] Windows: try WSL2 first (the Linux torch build that the numerical contract was checked on), then native Windows Python; every new platform needs the cross-GPU check (CUDA engine hashes equal, FP32 evaluation equal) before it is admitted; the code and the scripts (`ssh`, `pkill`, pid files, `setsid` in `cluster_runner.py`) have only run on Linux.
- [ ] Reach the coordinator from outside the home network: a private overlay (Tailscale) so that traffic is encrypted; the token travels in clear text over plain HTTP today (acceptable only on a private cable / LAN).
- [ ] Slow uplinks make the 1 GB synchronization the cost: measure replay `auto` there (the real use of the replay option).
- [ ] Trust: workers are trusted by design; a borrowed machine can return wrong rewards unseen. Idea: evaluate some candidates twice on two workers and compare. State it in the report.

## admission-in-the-join-flow  (owner agreed 08/10, after v0.5.0; to be built together with E1 of `ideas-remote-workers`, same "a new machine joins" flow)
- [ ] Today admission is a hand-run tool (`profile_worker.py` + `predict_admission.py`); `run_worker.py` checks only that the coordinator answers and that the recipe matches. Build the join flow: capability gate on the machine (versions, noise / CUDA self-tests, bit-exact restore, a reference candidate against golden hashes) + a QUICK profile (minutes: a short workload, a few candidates) + the benefit prediction, ending in ADMITTED / ADMITTED_LIMITED / ELIGIBLE_BUT_NOT_BENEFICIAL / INELIGIBLE with reasons.
- [ ] Keep the FULL profile (8 probe candidates, chunk 1 as reference, the experiment's own workload; hours on a 1660S) as the mode for evidence only, and say in the report that v0.5.0 admission is this hand-run tool.

## remote-workers-from-ADR-003  (proposed in `docs/adr/ADR-003-remote-workers-network.md`, 08/10 night; the owner decides)
- [ ] Replay as the way to join: `fetch_chain` stops at 8 steps; allow a long chain (a late worker replays from the base weights, downloaded from Hugging Face at the pinned revision) and a periodic checkpoint to bound it. Test with the second 3060 (another city).
- [ ] Tailscale ACL with tags (coordinator, worker) written before any borrowed machine joins; expiring keys for borrowed nodes.
- [ ] Refuse `--allow-unauthenticated` outside loopback or the direct cable in `cluster_runner.py` / `run_coordinator.py`; per-worker tokens.
- [ ] (if the owner wants independence from a vendor) hub-and-spoke WireGuard with a cheap VPS as the hub, compared with Tailscale on the same pairs of machines. Do not write an own VPN.
- [ ] Cross-check of 2 workers on a fraction of the candidates (trust in borrowed machines).

## scale-and-spread  (owner direction 09/10: many machines in many places, LAN to other cities; focus on NVIDIA GPUs, laptops included)
- [ ] **MacBook / Apple Silicon: NOTED, NOT NOW** (owner, 09/10). No CUDA there; it would need a portable noise engine (integer counter-based generator, no transcendental functions) and a cross-device numerical decision. Keep NVIDIA only until the rest works.
- [ ] Enrollment without Tailscale: "download, install, log in, the machine is a worker" (owner). Brainstorm of 09/10 in the chat; to become an ADR when the owner agrees. Constraints named: a future admin and users of track B (production), internet cafes with a few machines (probably no admin rights, outbound only, machines that reset).
- [ ] Hardware coming: a second 3060 (another city), a 5070 Ti, a 4060 (Ada: a new architecture for the cross-GPU qualification), then internet cafes. Each new GPU model must pass the numerical qualification before it is admitted.
- [ ] Scale by simulation: the real coordinator and ledger with hundreds of simulated workers (joining, leaving, slow), throughput of the coordinator, behaviour of the dispatch policies; say in the report that it is simulation.

## chunk-128  (agreed 09/10: for the NEXT session to run, after the N = 48/96 runs have finished and the GPUs are free)
Question: can the 128 questions of `cot_l1_q128` be answered in ONE `generate()` call (chunk 128) on every GPU, giving the same text as chunk 1, and is it faster? VRAM is not the limit (a candidate peaks at about 3.8 GB at chunk 64; 16, 12 and 6 GB cards).
1. **Exactness first** (if it fails, stop: no speed measurement is needed): `profile_worker.py --workload cot_l1_q128 --noise-engine cuda --chunks 1,128 --probe-candidates 8 --candidates 1` on each GPU (5070 Ti about 11 min, 3060 about 30 min, 1660S about 80 min and only if it is up). PASS = chunk 128 identical to chunk 1 on the parent and on all 8 perturbed candidates, on every GPU, and the same texts on the three GPUs (`scripts/cross_gpu_sweep.py` style comparison of the texts, not only of the rewards). Peak memory must fit the smallest card.
2. **Then the speed:** the time of a candidate at chunk 128 against 64 (the profiles give per-evaluation seconds of 128 questions at chunk 64: 5070 Ti 6.4 s, 3060 16.9 s, 1660S 28.4 s; the gain from chunk 16 to 64 on the 5070 Ti was only 1.9 times for 4 times the chunk, so the AI's guess, NOT measured, is 1.2 to 1.7 times for 64 to 128). Then B0 against T2 at N = 24 with chunk 128, same experiment id, same weights expected.
3. If it works, a per-worker chunk becomes meaningful only when the safe chunks of the machines differ (today all three are 64): keep `chunk per worker` as is.
4. **Reading (done 09/10):** nothing in the cuBLAS or PyTorch documentation guarantees equal results for different batch sizes or different GPU architectures (cuBLAS: bit-wise equality only for the same toolkit, the same architecture and the same number of SMs; PyTorch forum: determinism only for the same batch size). So every new chunk and every new GPU model (the 4060, Ada) needs its own probe; the equality seen on three GPUs is measured, not guaranteed. Option for later: batch-invariant kernels (Thinking Machines, Sept 2025), at a cost in speed, still to be checked across GPU architectures.
