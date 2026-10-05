# HeteroES-LLM — Status

**Last updated:** 06/10/2026 (step 8 done; step 7 done earlier; after decisions O4, eta and seed checks of 05/10; branch `feat/perturb-restore-update`, see 0.0). Section 0.0 is the newest; sections 1–13 were written on 30/09 and are older background — where they disagree with 0.0, 0.0 wins.  
**Canonical design/specification:** `HETEROES_LLM_MASTER.md`  
**Purpose:** current implementation truth, verified evidence, blockers, artifacts, and the exact next action.

> **Document rule:** `MASTER` decides what the system/design should be. `STATUS` decides what is actually done now. For a new chat, read `HETEROES_LLM_MASTER.md` and then this file; older proposal/roadmap/chat-handoff files are archive only.

## 0. NEXT SESSION — START HERE

### 0.0 Progress update — 05/10/2026 (perturb, bitwise restore, ES update, one candidate on both GPUs, manifest v1 frozen; step 9 left)

Branch `feat/perturb-restore-update`, built on `main` at `2bd2073`. At the end of the session the last commit was `fb28885` (the step 6 evidence); the branch was ahead of `origin/feat/perturb-restore-update` (last pushed commit `e852355`) and the folder `artifacts/regression/2026-10-06-cross-machine-one-candidate/` plus the documents of 06/10 were not committed yet. Check `git status -sb` and `git log` again.

- **Implemented and committed:** `src/heteroes/es/perturb.py` (`perturb_parameter_`, `perturb_model_`: contract O2 = (c), every check done before the first write), `src/heteroes/es/snapshot.py` (`take_snapshot`, `diff_from_snapshot`, `restore_from_snapshot_`, `RestoreError`; bitwise comparison through an int16 view, in slabs of `slab_elements`), `src/heteroes/es/checks.py` (shared input checks), and `resolve_tensors` plus `SchemaMismatchError` in `src/heteroes/model/schema.py`. Tests: `tests/es/test_perturb.py`, `test_perturb_model.py`, `test_snapshot.py` and `tests/model/test_resolve_tensors.py`.
- **Measured (5070 Ti only; torch 2.10, NumPy 2.4.5, Python 3.12):** `pytest tests` without the two step-5 test files gives 258 passed and 3 skipped. With the real model (`HETEROES_QWEN_PINNED_PATH` and `HETEROES_QWEN_PATH` pointing at the Hugging Face snapshot of `Qwen/Qwen2.5-0.5B-Instruct@7ae55760…`) it gives 261 passed. On the real model the package's `perturb_model_` (seed 0, sigma = float32(1e-3)) gives a whole-model hash that starts with `8aa3eb9af895cb4a`, the same as the four environments of 03/10, on the GPU and also with the GPU hidden (CPU only). Perturb followed by restore gives back the original bits (SHA-256 of all weights equal). The extra GPU memory during restore stays below 256 MiB (that bound is asserted in a test; the actual peak was not recorded).
- **Mutation checks (by hand on scratch copies, not automated):** perturb 15 deliberate faults, `perturb_model_`/`resolve_tensors` 16, snapshot 14. All were caught except equivalent mutants, i.e. faults that cannot change any result: the `float(np.float32(sigma))` line (PyTorch already rounds a Python scalar to float32; the line is kept on purpose), a `zip` without `strict=True`, and a sigma pre-check that passes `0.0` (sigma is the same for every tensor, so the first write already fails). Three gaps in my own tests were found this way and closed.
- **Not verified:** none of this package code has run on the 1660S yet (restore on 6 GB is untested); the real-model hash covers seed 0 and sigma = 1e-3 only. (Predictions and reward: see step 6 below, 5070 Ti only.)
- **Step 5 (reward standardization + FP32 ES update) is implemented (05/10 evening); the numerical checks are NOT done on the 1660S.** `src/heteroes/es/update.py` (`UpdateReport`, `standardize_rewards`, `apply_es_update_`) was written by the owner against the specification tests `tests/es/test_standardize.py` and `tests/es/test_update.py`. Two mistakes found by the first test run were fixed by the owner (a misplaced parenthesis in the `changed` count and `numel` taken from the last tensor instead of the whole model). Measured on the 5070 Ti (torch 2.10, NumPy 2.4.5): `pytest tests` with the real model (env vars as in `CLAUDE.md`) gives **325 passed**. Not measured: the run without the env vars, anything on the 1660S, seeds other than 0 to 3, sigma other than 1e-3, any effect on reward or learning.
- **Decided 05/10:** O4 = canonical FP16 epsilon upcast to FP32 (measurements and accepted trade-off in the contract section 8; monitoring of the rounding errors is future work, `TODO.md` group `monitoring`). **Also decided 05/10:** the seeds of one update must be real integers and pairwise distinct (contract section 3); O5 (where seeds come from) is deferred to step 8. **Also decided 05/10:** eta = 1e-9 (the notebook used 1e-8); `standardize_rewards` computes in float64 and returns float32. **Not yet approved:** the report fields of `UpdateReport` (they come from what `test_update.py` expects). A comparison with how other ES code handles rewards is in `docs/numerical-contract.md` section 7.1 (read through a page summarizer, not checked word for word).
- **Mutation check of `update.py` (by hand on a scratch copy of `src`, not automated):** 27 deliberate faults, all caught except two equivalent mutants (`acc` created in FP16 but PyTorch promotes the sum to FP32; `alpha` not rounded to float32 first, PyTorch rounds the scalar anyway). A real FP16 accumulation (M02b) is caught. The first run found three gaps in my tests (counting `changed` numerically instead of by bits, an invalid `chunk_elements`, and a length mismatch of seeds and rewards, both hidden behind a silent no-op when the rewards are equal); tests for them were added and the mutants are now caught. Uncommitted files at the end of the session: `CLAUDE.md`, STATUS, `TODO.md`, the contract, `docs/architecture.md`, `update.py`, `test_standardize.py`, `test_update.py`.
- **Measured 05/10 with scratch scripts (not in the repo; the numbers are in the contract section 8):** on the real model (all 494,032,768 elements, seeds 0 to 3, sigma = float32(1e-3), NumPy 2.4.5, CPU) the cast of epsilon to FP16 changes it by 2.08e-4 in relative L2 norm; the rounding of theta' (realized perturbation versus canonical epsilon) by 5.4e-3, with 0.405% of the elements unchanged. Limits and the open question (effect on learning) are in the contract and in `TODO.md`, group `monitoring`.
- **Tests added 05/10 (specification, written by the AI):** `tests/es/test_update.py` also checks seed types (`float`, `bool`, `str`, `None` raise `TypeError`), that `[1, "1"]` is refused, that NumPy integer seeds behave like Python integers and that `[1, np.int64(1)]` is a duplicate; that an invalid `chunk_elements` or a length mismatch is rejected even when the rewards are equal; and that `changed` is counted by raw bits (a flip of -0.0 to +0.0 counts).
- **Step 6 (one candidate end to end) is done on the 5070 Ti only (05/10 night).** New: `src/heteroes/eval/workload.py` (the 16-prompt workload of the probe, `extract_integer`, exact-match reward, `workload_hash`), `src/heteroes/eval/generate.py` (`generate_answer`, `evaluate_model`), `src/heteroes/eval/candidate.py` (`run_candidate`, `model_weights_sha256`) and `scripts/run_one_candidate.py` (JSON record with environment, commit, model, generation config; refuses to overwrite a file and refuses a model directory that is not the pinned revision). Commits `f036ca6` (6a, 6b) and `30275cd` (6c). The tests were written first by the AI (with a reference implementation in a scratch copy, only to prove that they can pass); the owner approved the code before it entered the repo. Evidence: `artifacts/regression/2026-10-05-one-candidate/` (two processes, two runs each, so the same candidate ran four times). Measured: schema hash, workload hash and the whole-model hash of the perturbed weights (`8aa3eb9af895cb4a...`) equal to the earlier evidence; base outputs equal to the probe of 29/09 text for text (reward 0.25); restore bit for bit; outputs after restore equal to the base outputs; all four runs identical. The candidate (seed 0, sigma 1e-3) scores 0.3125 and changes the text of 10 of the 16 answers: one candidate and 16 prompts say nothing about learning. `pytest tests` with the real model: **404 passed** (about 107 s); without the env vars 390 passed and 14 skipped (5070 Ti). Mutation check by hand on scratch copies: 12 faults for `workload.py` (11 caught, the 12th revealed a gap that was closed), 13 for `generate.py` (all caught), 29 for `candidate.py` and the script (all caught but one equivalent mutant: reading the bits through an int16 view or as FP16 gives the same bytes). `git_dirty` is true in the JSON files: the only untracked path was an unrelated notebook (see the README of the folder).
- **Found in step 6:** the checkpoint's `generation_config.json` has `repetition_penalty` 1.1 and sampling flags; transformers reports that `temperature`, `top_p` and `top_k` are ignored when `do_sample=False`, while the repetition penalty stays in the recorded configuration (hash `05744820...`). The checkpoint is stored in bfloat16 and loaded as FP16. Records of the other machine must show the same generation config hash.
- **Step 7 (same candidate on the 1660S) is done (06/10, early morning).** The owner authorized SSH to the 1660S for this step (password login; no key was installed, nothing was saved). The unpushed commits were sent as a `git bundle` (SHA-256 checked) and `30275cd` was checked out detached on the 1660S (clean tree, same commit as the 5070 Ti run). There: `pytest tests` with the real model gives **404 passed in 471 s** (same count as the 5070 Ti, 107 s), and `scripts/run_one_candidate.py` (seed 0, sigma 1e-3, `--repeat 2`, two processes) gives records that are identical to each other. Compared with the 5070 Ti records: schema, workload, engine, chunk size, seed, sigma, model and tokenizer revision, and the three whole-model weight hashes (original `c9118c8a...`, perturbed `8aa3eb9af895cb4a...`, restored) are **equal**; the outputs of the 16 questions of the base model, of the candidate and of the restored model are **equal text for text**; rewards 0.25, 0.3125, 0.25 on both; every pair of files (each 5070 Ti file against each 1660S file) agrees. Machines: 5070 Ti (cc 12.0, Python 3.12.13, torch 2.10, NumPy 2.4.5, transformers 5.5.0) and 1660S (cc 7.5, Python 3.14.4, torch 2.13, NumPy 2.5.2, transformers 5.17.0). Same `model.safetensors` blob on both. Evidence and README: `artifacts/regression/2026-10-06-cross-machine-one-candidate/`. So the checks of the cross-machine gate (contract section 9) hold for ONE candidate on these two machines: noise and perturbed weights, restore on both, the 16 predictions, the reward. Limits: one seed, one sigma, 16 prompts, greedy decoding, two machines; not a universal guarantee.
- **Found in step 7:** the hash of the whole `generation_config` dict differs between the machines (`05744820...` and `8fb3597a...`) only because transformers 5.17 adds four keys with value `None` and stores its own version; the set values are identical. The comparison script therefore compares the SET values and shows the raw hash as information. That rule was first chosen by the AI after it saw the difference; the owner approved it on 06/10 (step 8) and it is now the rule of the manifest. The 1660S has leftovers in `/tmp` (bundle, logs, outputs), a new local branch `feat/perturb-restore-update` and a detached HEAD at `30275cd` (its old branch is untouched).
- **Step 8 (manifest v1 frozen) is done (06/10).** The owner approved the design: two layers, pin the behaviour and not the NumPy version, explicit seeds, the set values of the generation config. New (contract section 12): `src/heteroes/canonical.py` (the ONE serialization for hashes, now used by the schema hash, the workload hash and the manifest), `src/heteroes/noise/selftest.py` (noise fingerprint of five golden chunks, 13 ms on the 5070 Ti), `src/heteroes/manifest.py` (`Recipe`, `CandidateDescriptor`, `derive_seed`, `effective_generation_config`), `scripts/compare_candidate_records.py` (now in the repo; compares by recipe hash, lists measured differences), and `scripts/run_one_candidate.py` writes record format 2 (recipe, recipe hash, descriptor, noise self-test result; it refuses to run if the self-test fails). **O5 decided:** seeds are explicit data in the descriptor, range `0 <= seed < 2^53`; the coordinator chooses them, preferably with `derive_seed` (not part of the cross-machine contract); the regression keeps `[0..3]`. **O6 decided:** no NumPy version is pinned; the recipe holds the noise fingerprint and each worker runs the self-test (the version is only reported). The recipe hash built from the records of the 5070 Ti and of the 1660S is the same, `1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1`; with a NumPy version in the hash they would differ (2.4.5 and 2.5.2). `alpha` is not in the recipe (a parameter of each generation). Measured on the 5070 Ti: `pytest tests` with the real model **535 passed** (about 107 s), 521 passed and 14 skipped without the env vars. The tests were written first by the AI (in a scratch copy, with a reference implementation), approved by the owner and then copied; mutation check by hand on the scratch copy: 33 faults, all caught but one equivalent mutant (the explicit label check in `Recipe.from_dict` is also caught by the round-trip check). Pinned values in the tests (recipe hash, noise fingerprint, derived seed) were produced by this code: regression guards, not independent evidence; the five golden digests are evidence of four environments. Limits: the format-2 script has not been run on the 1660S (the evidence of 05/10 and 06/10 has format 1 and was checked offline); the self-test is not yet part of a worker admission.
- **Next action:** (1) commit the step 8 files and the documents when the owner asks; (2) step 9: this section is updated; (3) optional: run the format-2 script on both machines (SSH needs a new authorization from the owner) and store the records in a new folder; (4) after the gate, the roadmap: the record of a generation (descriptors, coefficients, alpha, parent weights) with the candidate/attempt/lease model and the SQLite ledger, written test-first on the CPU with fake workers, then the HTTP worker and coordinator and a frozen two-node generation; a short learning experiment on one GPU is proposed early (the biggest scientific risk). Small open items: `TODO.md`, groups `update-polish`, `step6-polish`, `manifest-next`, `dedupe`, `monitoring`.

### 0.1 Earlier progress — 03/10/2026 (CanonicalNoiseEngine v1 implemented; superseded by the section above)

State at commit `50a8bd4`, pushed to `origin` (`git@github.com:Anakonkai01/hetero-es.git`, branch `feat/canonical-noise-engine`). The engine itself was complete at `21b14e1`; later commits added the cross-GPU script (`7b73e03`), the evidence (`b34788f`) and the O2 decision (`50a8bd4`).

- **Implemented:** `src/heteroes/noise/contracts.py` (`ENGINE_VERSION`, `DEFAULT_CHUNK_ELEMENTS`, `ChunkNoiseAddress`, `ParameterNoiseAddress`) and `src/heteroes/noise/engine.py` (`derive_chunk_seed`, `generate_chunk_noise`, `num_chunks`, `chunk_length`, `iter_parameter_noise_chunks`, `generate_parameter_noise`). `pytest tests`: 116 passed, 1 skipped (the real-Qwen-layout test S9, which needs `HETEROES_QWEN_PATH`). Tests were mutation-checked by hand on scratch copies (about 40 deliberate faults, all caught); this is not automated in CI.
- **Verified on the 5070 Ti host only (NumPy 2.4.5, Python 3.12):** with the probe schema hash as input the new engine reproduces the full probe result: 2,105 chunks, 494,032,768 elements, global hash `816c15300c45ca9e85468b7787bc4ce313a87d1e74e6429e48eb9e6d357dafda` (the value both physical machines recorded on 29/09). That check was a scratch script and is not in the repo yet (candidate for a slow test). The 5 probe golden vectors and the real-embedding stream (520 chunks) are in the test suite.
- **Production golden vectors** (5 chunks addressed with the production schema hash `0b21250e…`) are in `tests/noise/test_engine.py`. They were produced by this engine itself, so they are a **regression guard only, not independent or cross-machine evidence**.
- **Done later on 03/10/2026 (evening): cross-machine check, including the 1660S.** Evidence and README in `artifacts/regression/2026-10-03-o2-perturbation/`; script `scripts/o2_cross_gpu_check.py`, commit `7b73e03`. `pytest tests` passes (117 tests) on the 5070 Ti and on the GTX 1660 SUPER (Python 3.14.4, NumPy 2.5.2, torch 2.13). The script (a copy of the engine plus the perturbation study) also passed all checks on a Colab T4 and a Kaggle T4 (NumPy 2.1.3). In all four environments: 10 golden vectors, layout and schema hashes, the full-model noise hash `816c15300c45ca9e…` (2,105 chunks) and the production schema hash match. So the production golden vectors are now cross-machine evidence (engine and recipe), no longer only a regression guard.
- **O2 decided (option c):** `fp16( fp32(θ) + fp32(σ)·fp32(ε) )` with each step a separate operation. The perturbed weights of all 494,032,768 elements have the identical whole-model hash (`8aa3eb9af895cb4a…`) for GPU, CPU (NumPy and torch), whole tensor or per chunk, in the four environments (RTX 5070 Ti, GTX 1660 SUPER, Colab T4, Kaggle T4). Alternative (a), `add_(alpha)`, was also identical across the four environments (`ce33fa32…`) and is kept as a noted alternative; it differs from (c) in 167 elements, and its CPU version differs from its GPU version in about 9.6 to 9.9% of the elements. All-FP16 steps and CPU `add_` are not portable (cause unknown). Details and limits in `docs/numerical-contract.md` section 5. **Limits:** one seed, one σ, four x86_64 Linux environments, computed by a script (no perturb function in the package yet). Warning (inference, not verified): fusing the multiply and the add into one kernel, or `torch.compile`, could change the bits.
- **Cross-machine gate status (03/10; see 0.0 for 05/10):** noise bytes and perturbed-weight hashes are covered on the 1660S (and the three other environments); restore, the 16 predictions and the reward are NOT done on the 1660S yet.
- **Not done:** perturb / restore functions in the package (the arithmetic is decided, O2 = c, and the bitwise oracle is decided, O3; neither has a package function yet), FP32 ES update (O4 decided 05/10, see 0.0), seed rule (O5 open), NumPy pin (O6 open, check the 1660S wheel), `SchemaEntry.__post_init__`, `to_json` / `from_json`, `verify_model_matches`, cross-machine same-candidate regression. Code-level TODOs: `grep -rn TODO src/`.
- **Next action:** write the perturb function in the package using option (c) (test: bit-identical to the NumPy method; test that it does not use `add_(alpha)`), then bitwise restore from a snapshot (chunked so it fits the 6 GB worker), then the same-candidate regression (predictions, reward, restore) on both GPUs.

### 0.2 Earlier progress — 02/10/2026 (ParameterSchema; superseded by the sections above)

- `docs/architecture.md`, `docs/numerical-contract.md`, `docs/adr/ADR-001` are merged on `feat/canonical-noise-engine` (drafts; the owner has not reviewed every rule). Decisions taken: **O1** schema hash includes aliases + `schema_version`; **O3** restore oracle is bitwise. Open: O2 (perturbation arithmetic, settled by the cross-machine gate), O4 (epsilon used in update), O5 (seed rule), O6 (pin one NumPy version, check the 1660S wheel).
- **Implemented:** `src/heteroes/model/schema.py` — `find_alias_groups`, `SchemaEntry`, `ParameterSchema`, `build_parameter_schema`; 27 tests in `tests/model/test_schema.py` (S9 real-layout test runs only with `HETEROES_QWEN_PATH`). 12 deliberate mutations of the code are all caught by the tests.
- **Verified on real Qwen layout (local checkpoint, 5070 Ti host only):** 290 entries, 494,032,768 elements, one alias group (`model.embed_tokens.weight` + `lm_head.weight`); the probe-format schema hash `152e9d82…` is reproduced; production schema hash is `0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec`. (Update 03/10: S9 also passed on the 1660S, see `artifacts/regression/2026-10-03-o2-perturbation/1660s_pytest.txt`.)
- **New evidence/fixes to earlier claims:** the five golden vectors reproduce under NumPy 2.4.5 (env `ai`); PyTorch docs state that reproducibility is not guaranteed across platforms and a forum thread reports `torch.rand` diverging across 3090/A100/H100 for large tensors (sources in ADR-001). The CUDA-RNG probe is one seed / one run per machine, so its scope is limited (see ADR-001).
- **Not done:** `__post_init__` validation, `to_json`/`from_json`, `verify_model_matches`; production `CanonicalNoiseEngine`; golden vectors for the production hash; everything after step 2 of the implementation order (§11). Code-level TODOs: `grep -rn TODO src/`.
- **Next action (done on 03/10, see 0.0):** `src/heteroes/noise/contracts.py` + `engine.py` (CanonicalNoiseEngine) with the golden-vector test, using the production schema hash.

The project has moved beyond Colab-only work. **Both physical GPU machines are on Ubuntu 26, remotely manageable over Tailscale + OpenSSH, and both can run the modified Qwen2.5-0.5B-Instruct FP16 single-GPU ES reference end-to-end.** The major numerical discovery is that native CUDA RNG is **not portable enough for seed-only cross-worker replay**: the RTX 5070 Ti and GTX 1660 Super produced different noise bytes and different perturbed candidate predictions even after Torch/CUDA/Transformers were matched. A new CPU-based **Canonical NoiseEngine v1** was then probed over the full 494,032,768-parameter model and produced **identical noise bytes on both machines**.

**Exact next task:** preserve the current mixed-output notebook as a historical artifact, start a clean reference/package path, and turn the successful `heteroes_noiseengine_probe.py` recipe into a production-ish `CanonicalNoiseEngine` module. In the same refactor, pin the verified model revision, fix the known schema/alias/error-path issues, make ES update accumulation FP32, and route both candidate perturbation and coordinator-side reconstruction/update through the **same** engine. Then produce a clean single-GPU artifact and run the cross-machine same-candidate regression. **Do not start FastAPI/two-node scheduling before this regression passes**, because distributed ES correctness depends on candidate identity first.

Target next regression:

```text
Same model revision / FP16 / schema / candidate seed / sigma
        |
        +--> 5070Ti CanonicalNoiseEngine --> perturbed candidate
        |
        +--> 1660S  CanonicalNoiseEngine --> perturbed candidate

Compare:
- noise hash
- perturbed weight sample hashes
- 16 candidate predictions
- candidate reward
- canonical restore diff

Required before distributed generation:
- same noise bytes: PASS
- same perturbed sampled weights: PASS
- restore exact on both: PASS
- any inference-output difference must be measured/explained, not hidden
```

After that regression, the next milestone is the **frozen two-node generation**: coordinator/update executor on 5070 Ti; candidate evaluation split across 5070 Ti and 1660 Super; workers return reward/result only; only the coordinator reconstructs/aggregates and publishes canonical model v1.

## 1. Team, product, and ownership

The project is a two-person capstone. Current canonical split:

- **A — Systems/Core owner (hardware owner):** ES numerical core, CanonicalNoiseEngine, physical 5070Ti/1660S deployment, worker runtime, coordinator internals, candidate/attempt/lease/ledger, C1 admission, C2 candidate scheduling, C3 failure correctness, C4 sync/replay, GPU/network profiling and experiments.
- **B — Product/Application owner:** self-hosted login/session, lab workspace + memberships + Admin/Researcher/Viewer, experiment ownership, non-preemptive experiment-level queue, cluster/live-run/results/artifact UX, usage visibility, product API/integration. B should develop against mock runtime schemas and does not need to own GPUs.

Important boundary: **B's experiment queue is not C2 candidate scheduling.** The product queue selects which user experiment may start; after a run starts, worker admission/candidate dispatch/attempts/leases are A's systems domain.

Target user story: a low-budget lab with several members sharing a small heterogeneous consumer-GPU pool. Product scope is self-hosted lab use, not public SaaS/billing/enterprise SSO.

## 2. Physical machines and remote administration

### 2.1 RTX 5070 Ti machine

```text
hostname: 5070ti
Ubuntu: 26.04.1 LTS
GPU: NVIDIA GeForce RTX 5070 Ti, ~16 GB
NVIDIA driver: 595.91.07
matched probe env: conda env `heteroes-match`
Python: 3.12.14
PyTorch: 2.13.0+cu132
Torch CUDA runtime: 13.2
Transformers: 5.17.0
GPU capability: (12, 0)
NumPy in full NoiseEngine probe: 2.5.3
```

An older working conda env `ai` also exists (`Python 3.12.13`, `torch 2.10.0+cu128`, `Transformers 5.5.0`). Keep it as historical/working environment; do not overwrite it. `heteroes-match` was created specifically to control the runtime comparison with the 1660S.

### 2.2 GTX 1660 Super machine

```text
hostname: heteroes-worker-1660s
Ubuntu: 26
GPU: NVIDIA GeForce GTX 1660 SUPER, 6 GB
NVIDIA driver observed: 595.91.07
Python env: ~/projects/heteroes/.venv
Python: 3.14.4
PyTorch: 2.13.0+cu132
Torch CUDA runtime: 13.2
Transformers: 5.17.0
GPU capability: (7, 5)
NumPy in full NoiseEngine probe: 2.5.2
```

The 1660S originally OOMed with the earlier FP32/reference path at perturbation, but the **modified FP16 notebook/reference subsequently ran full successfully**. Do not preserve the earlier OOM as a current blocker; retain it only as evidence that dtype/headroom matters for low-VRAM workers.

### 2.3 Network/SSH state

Both machines use **Tailscale for private IP connectivity and normal OpenSSH + SSH keys for shell access**. On the 5070Ti, Tailscale SSH was deliberately disabled because its `check` mode forced browser re-authentication. Tailscale networking remains enabled. During setup, Tailscale reported direct peer paths rather than relay for the active machines.

Management model:

```text
Omarchy laptop
    | Tailscale private network
    +--> OpenSSH --> 5070ti
    +--> OpenSSH --> heteroes-worker-1660s
```

SSH is for setup/debug/deploy only. The future HeteroES runtime must use its own HTTP/service protocol; candidate dispatch must not depend on SSH.

## 3. Single-GPU ES reference — verified

Reference/model: `Qwen/Qwen2.5-0.5B-Instruct`. The current physical baseline uses **FP16**. Core recipe is one-point Gaussian ES with reward standardization; current smoke workload is 16 arithmetic problems with exact-integer-match reward.

Verified implementation/evidence:

- [x] perturb -> candidate evaluation -> rewards -> standardize -> ES update pipeline.
- [x] normal reward standardization.
- [x] equal rewards -> zero/no-op update.
- [x] NaN/Inf reward rejection.
- [x] `evaluate_candidate_v2()` and `evaluate_population_v2()`.
- [x] canonical full-model restore instead of arithmetic subtract-noise as correctness reference.
- [x] one-generation update and `run_es_generation()`.
- [x] three consecutive generations.
- [x] model remains operational after permanent update.
- [x] checkpoint save/reload.
- [x] full modified notebook/reference runs on both physical GPUs.

Historical 3-generation smoke from the earlier reference:

```text
Gen 0: candidate mean = 0.2031, std = 0.0518
Gen 1: candidate mean = 0.2188, std = 0.0312
Gen 2: candidate mean = 0.2344, std = 0.0271
Base reward: 0.25 -> 0.25 -> 0.25
All candidate restores exact: True
```

This still does **not** prove learning improvement. The 16-sample exact-match set is too small and base reward did not improve.

## 4. Model/schema/canonical-state evidence

Current Qwen path:

```text
model revision: 7ae557604adf67be50417f59c2c2f167def9a775
parameter tensors: 290
parameter elements: 494,032,768
FP16 schema SHA256: 152e9d82e61d6610a414466026ac60a13e718924dfdf0416809686adcf4188e1
16-example workload SHA256 from compatibility probe:
cad822bc1e65a9ec37d948e5415cff22c70f96500e2043e6299bbdd5cea0b8d5
```

The newer probe found **1 alias/tied parameter group** using the corrected condition `len(names) > 1`. The older notebook result of zero groups came from a bug that only reported groups with more than two aliases (`len(names) > 2`). Treat the newer probe as canonical evidence.

Canonical restore remains exact in current probes:

```text
restore max diff = 0.0
restore worst = None
```

## 5. C4 numerical/replay discovery — verified 29/09/2026

### 5.1 Compatibility probe before runtime matching

Using the same Qwen revision, FP16 model, schema and 16-example workload:

```text
5070Ti: torch 2.10.0+cu128 / CUDA 12.8 / Transformers 5.5.0
1660S : torch 2.13.0+cu132 / CUDA 13.2 / Transformers 5.17.0
```

Comparison:

```text
same_model_id              PASS
same_model_revision        PASS
same_dtype                 PASS
same_schema                PASS
same_parameter_count       PASS
same_weight_samples        PASS
same_workload              PASS
same_noise_stream_sample   DIFF
same_noise_target_hashes   DIFF
same_base_reward           PASS
same_candidate_reward      PASS
same_base_predictions      PASS
same_candidate_predictions DIFF
left_restore_exact         PASS
right_restore_exact        PASS

Structural contract match: True
Behavior match: False
Replay probe pass: False
```

Important interpretation: equal candidate reward did **not** imply the same logical candidate; candidate predictions already differed. Exact-match reward was too coarse to detect the mismatch by itself.

### 5.2 Controlled matched-runtime probe

A new 5070Ti conda env `heteroes-match` was created to match the 1660S on:

```text
PyTorch     2.13.0+cu132
CUDA runtime 13.2
Transformers 5.17.0
FP16
model revision / schema / workload
```

The result stayed the same:

```text
same_noise_stream_sample   DIFF
same_noise_target_hashes   DIFF
same_candidate_predictions DIFF
restore exact on both      PASS
```

Therefore the project must **not** use native `torch.randn_like(..., device="cuda") + seed` as cross-worker candidate identity. The controlled evidence proves the current CUDA-native recipe is not portable across these two worker setups. It does not claim a universal theorem that all different GPU architectures always differ.

5070Ti matched-probe example:

```text
Base reward: 0.25
Candidate reward: 0.25
Noise stream sample SHA256:
6839fde5475fc81cb0050a19cdc381caf0fc9eaa1af325fb83cf4137fc6c20b0
Restore max diff: 0.0
```

### 5.3 Canonical NoiseEngine v1 full-model probe

A CPU-based canonical recipe was then tested:

```text
engine version: numpy_pcg64_normal_f32_to_f16_v1
logical identity:
  candidate seed
  model schema hash
  parameter index
  chunk index
  fixed chunk_elements
chunk seed: SHA-256-derived, first 128 bits little-endian
PRNG: NumPy PCG64
distribution: standard normal
generation dtype: FP32
application/storage bytes: FP16
```

Full mode covered the full model (290 tensors / 494,032,768 parameter elements). Comparison:

```text
LEFT : 5070ti | numpy=2.5.3 | torch=2.13.0+cu132
RIGHT: heteroes-worker-1660s | numpy=2.5.2 | torch=2.13.0+cu132

same_engine_version : PASS
same_numpy_version  : DIFF
same_model          : PASS
same_model_revision : PASS
same_schema         : PASS
same_candidate_seed : PASS
same_chunk_size     : PASS
same_mode           : PASS
same_noise_bytes    : PASS
```

**Verified conclusion:** Canonical NoiseEngine v1 generated identical tested full-model noise bytes on the two physical machines despite different GPU architecture and the observed NumPy patch-version difference. Production policy should still record/pin NumPy version rather than assuming future-version compatibility.

This is currently the strongest C4 numerical evidence in the project.

## 6. Current code reality, notebook audit, and artifacts

### 6.1 What code actually exists now

> **Update 03/10/2026:** the package now exists for the first two layers — `ParameterSchema` and `CanonicalNoiseEngine` v1 with 117 tests (see 0.0). Perturb, restore, ES update and everything distributed below are still not implemented. The paragraph below is the 30/09 state.

As of 30/09/2026, the **actual HeteroES implementation is still primarily the modified notebook/reference plus probe scripts**. There is not yet a production `src/heteroes/...` package, worker/coordinator service, durable ledger, scheduler runtime, or integrated production `CanonicalNoiseEngine`. Do not infer implementation from MASTER roadmap text.

The uploaded/current notebook is `ES_Milestone1_2_modified.ipynb` (the conversation upload may carry a duplicate suffix). It remains useful as the numerical prototype, but its saved outputs are **not a clean single-session Run-All artifact**:

- model/tokenizer are loaded by model ID without `revision=` pinned inside the notebook;
- saved outputs include a `reloaded_tokenizer` `NameError` in one reload cell;
- saved outputs include a 1660S CUDA OOM while a full-parameter diff copies a large reference tensor back to GPU;
- saved outputs include `generation_log` / `run_es_generation` `NameError` cells from stale execution state;
- other later/independent physical runs did succeed, so these saved notebook errors **do not revoke the verified physical evidence**, but the `.ipynb` file itself must not be presented as `restart kernel -> Run All -> PASS` yet;
- `find_parameter_aliases()` in the notebook uses `len(names) > 2`; this is the historical bug behind the saved zero-alias result. The newer probe result of one alias group is canonical;
- `restore_canonical_parameters()` has a shape-mismatch error branch that references undefined `source.shape`;
- `es_update_direction()` allocates `torch.zeros_like(param)`, so the current FP16 notebook accumulates the ES direction in FP16; production should accumulate FP32 and cast/apply once;
- perturb/reconstruct/update still contain duplicated CUDA RNG logic, now obsolete for canonical cross-worker identity;
- the notebook's fixed seed list can be retained for regression/frozen benchmarks, but production candidate identity should include generation/candidate namespace rather than accidentally reuse the same population forever.

**Interpretation:** notebook = historical/numerical reference; probes = current compatibility evidence; next production code should move correctness-critical logic into modules/tests rather than adding distributed features inside the notebook.

### 6.2 Focused prior-art code audit — 30/09/2026

The source audit reinforced, rather than changed, the current architecture:

- **ES-at-Scale current main:** local Ray + static-wave candidate evaluation; engine 0 reconstructs update then broadcasts. Its archive already has completion-driven `ray.wait` dispatch, so B3 dynamic dispatch is a baseline. Current worker RNG resets a device generator from the same candidate seed per parameter; restore is arithmetic `-noise`; update accumulation is FP32; reward timeout is converted to 0.0. Learn the FP32/update and execution patterns, but do not copy its RNG/restore/failure semantics as canonical contracts.
- **Understanding-ES:** stable tensor-name namespace, shared-parameter dedup, FP32 noise/update, local update reconstruction and periodic sync. However it deliberately requires homogeneous engines on one host, uses static seed shards, and still derives noise with device/CUDA `torch.Generator`.
- **Agentic-ESOpt:** stable tensor IDs, chunked FP32 noise/update and atomic optimization `history.json` replay/resume are useful patterns. It also still uses device/CUDA RNG; its history replay is not a candidate/attempt/lease ledger and does not provide exactly-once distributed commit semantics.

Stable design consequence: **seed replay/local reconstruction are prior art; portable candidate identity across the tested heterogeneous GPUs plus C1 admission, C3 failure correctness and measured heterogeneous C4 consistency remain the HeteroES engineering focus.**

### 6.3 Important probe/reference files and artifacts

Source/probe files used so far:

```text
ES_Milestone1_2_modified.ipynb    # numerical prototype/reference; not yet clean Run-All artifact
heteroes_compat_probe.py          # physical/runtime/model/CUDA-RNG compatibility probe
heteroes_noiseengine_probe.py     # canonical CPU NoiseEngine sampled/full probe
```

Artifacts that should be preserved in the repo experiment/artifact area, not overwritten:

```text
probe_5070ti.json
probe_1660s.json
probe_5070ti_matched.json
comparison_matched.json
noiseengine_5070ti_full.json
noiseengine_1660s_full.json
```

Also preserve the earlier unmatched-runtime comparison if still present; rename it descriptively rather than overwriting. Exact filenames are less important than keeping raw JSON + environment metadata + commit/config. Preserve the current notebook before cleanup/refactor so stale-output history is not silently rewritten into new evidence.

## 7. Current canonical numerical decisions

- Physical baseline dtype: **FP16** for the current two-GPU reference path.
- Model: `Qwen/Qwen2.5-0.5B-Instruct`, pinned revision from probe.
- One-point Gaussian ES + reward standardization remains the core recipe.
- `sigma ~= 1e-3` remains the provisional exploration scale from earlier experiments.
- Canonical restore is full snapshot/restore with explicit exact-diff verification.
- Native CUDA RNG may still be used for local experiments, but **not as the canonical cross-worker replay contract**.
- Canonical candidate noise must go through the single versioned CPU-based NoiseEngine recipe until/unless a different engine is justified by evidence.
- The same NoiseEngine implementation must serve worker perturbation, coordinator reconstruction, ES update and replay/debug paths.
- ES direction/update accumulation should be FP32 even when the model baseline is FP16; cast/apply only at the declared boundary and record applied-update diagnostics.
- Parameter schema identity must include alias/tied-weight mapping; the older notebook schema hash is not the final production schema contract.
- Exact restore/diff verification must be memory-safe on the 6 GB worker; chunked comparison is allowed, weakening the exact oracle is not.
- NumPy version, engine version, model revision, schema hash, dtype, chunk size, seed namespace and sigma belong in manifests/candidate descriptors.

## 8. Distributed system state — not done yet

Despite the strong physical/numerical progress, the following are **not implemented/verified yet**:

- [ ] production `CanonicalNoiseEngine` module integrated into ES reference (module done and verified on 4 environments on 03/10; perturb/restore/update do not use it yet).
- [ ] cross-machine same-candidate regression using production engine (noise bytes and perturbed-weight hashes done on 03/10; predictions, reward, restore not done).
- [ ] remote HeteroES worker service / health / capability endpoint.
- [ ] frozen two-node generation.
- [ ] SQLite/WAL durable ledger.
- [ ] logical `candidate_id` separate from `attempt_id`.
- [ ] lease/expiry/retry.
- [ ] duplicate result / lost-ACK idempotency.
- [ ] stale attempt rejection.
- [ ] wrong model/noise/config-version rejection.
- [ ] generation expected-set/commit barrier.
- [ ] fake fast/slow/flaky worker campaign.
- [ ] C1 capability/safe-chunk/benefit-aware admission.
- [ ] B0/B1/B2/B3/H0 experiments.
- [ ] full-sync vs replay cost experiment across the real network.
- [ ] worker-loss/late-result/wrong-version fault campaign.
- [ ] final held-out learning evaluation.

## 9. Product/Application state — B's track

Design/ownership is defined, but product features are not marked implemented unless B has separate evidence. Planned Product Core:

- [ ] login/session;
- [ ] lab workspace; memberships; Admin/Researcher/Viewer;
- [ ] cluster/worker dashboard and admission reasons;
- [ ] Add Worker/onboarding UX;
- [ ] experiment ownership + My/Lab Experiments;
- [ ] non-preemptive experiment-level queue;
- [ ] live generation/candidate-attempt/failure visualization;
- [ ] result/artifact browser;
- [ ] usage visibility;
- [ ] product/runtime API integration.

B should start with mock contracts/wireframes and must understand candidate vs attempt vs lease well enough to present runtime state correctly.

## 10. Roadmap mapping after this session

| Area | Status now |
|---|---|
| Single-GPU ES reference | **Physical run evidence verified on both GPUs**; uploaded notebook itself still needs a clean restart/Run-All artifact |
| Physical compatibility | **Pass** for Qwen load/inference/full reference on 5070Ti + 1660S |
| Parameter/model structural contract | **Pass** across both probes |
| Canonical restore | **Pass, exact** on both |
| CUDA-native seed replay | **Fail for cross-worker identity**; do not use as canonical C4 replay |
| Canonical NoiseEngine v1 probe | **Full-model PASS for identical noise bytes** across the two physical machines |
| Production NoiseEngine module | **Done 03/10** — package module + tests; full-model noise hash and production golden vectors identical on 5070 Ti, 1660S, Colab T4, Kaggle T4 |
| Perturbation arithmetic (O2) | **Decided 03/10: option (c)** — whole-model perturbed-weight hash identical on the same 4 environments (computed by script) |
| Perturb / restore / FP32 update in the package | **NEXT** |
| Two-node generation | Not yet |
| C3 ledger/failure semantics | Not yet |
| C1/C2 experiments | Not yet |
| C4 cost/full-sync-vs-replay experiment | Numerical prerequisite underway; transport/cost experiment not yet |
| Product Core | Ownership/scope defined; implementation evidence not yet recorded here |

The old rough whole-project estimate (~23%) is now stale because physical compatibility and a key C4 blocker were resolved after that estimate. **Do not quote a new percentage until the roadmap is re-estimated deliberately.**

## 11. Immediate implementation order for A

1. **Preserve the current notebook as a historical artifact**, then make a clean reference branch/copy rather than overwriting mixed saved outputs.
2. Clean the reference contract before distributed work: pin model/tokenizer revision, fix alias detection, include alias mapping in schema identity, fix the undefined `source.shape` error path, and make exact diff memory-safe on the 1660S.
3. Convert `heteroes_noiseengine_probe.py` logic into production-ish module(s), e.g. `src/heteroes/noise/engine.py` plus contract dataclass/schema. This is the point to begin the real package; do not grow the notebook into the distributed framework.
4. Refactor all duplicated CUDA RNG paths so candidate perturbation and ES update/reconstruction consume the exact same `CanonicalNoiseEngine` API. Make ES update accumulation FP32.
5. Unit-test seed derivation, parameter/chunk independence, alias/schema mismatch rejection, same chunk bytes, deterministic replay, exact restore and FP32-update behavior.
6. Produce a **clean single-GPU reference artifact** from a fresh process/kernel with pinned manifest; no stale cells/errors in the evidence run.
7. Run the same-candidate regression on both physical GPUs; compare noise hash, perturbed sampled-weight hashes, all 16 predictions, reward and restore. Any inference difference after identical weights must be measured separately rather than hidden by equal reward.
8. Freeze candidate/noise manifest fields and generation/candidate seed namespace.
9. Only then create minimal worker/coordinator HTTP health/capability/evaluate path.
10. Run one remote candidate, then a frozen two-node generation with fixed parent/candidate set; **only the 5070Ti/coordinator publishes the update**.
11. After frozen generation correctness, implement durable SQLite ledger + candidate/attempt/lease semantics and deterministic fake-worker fault tests.
12. Then measure C1/C2 and full-sync-vs-replay cost.

## 12. Known limitations / claim boundary

- No heterogeneous two-node ES generation has completed yet.
- The current uploaded notebook is a mixed-output prototype, not yet a clean `restart -> Run All -> PASS` artifact; successful physical runs are tracked separately from this file-state limitation.
- No durable candidate/attempt/lease correctness implementation yet.
- Current arithmetic smoke/eval set is only 16 examples; no demonstrated task-learning improvement.
- Full-model Canonical NoiseEngine probe proves the tested noise bytes matched on the two current machines/configs; it is **not** a universal reproducibility guarantee for every CPU/NumPy/platform.
- Even with identical candidate weights, heterogeneous GPU inference may still produce small numerical/output differences; the next candidate regression must measure this separately.
- No evidence yet for cluster speedup, `ClusterBenefit`, forced-admit quality, B1/B2/B3 performance, failure recovery, or replay bandwidth/computation benefit.
- Dynamic dispatch is a baseline/integration mechanism, not claimed novelty.

## 13. Canonical-document policy

Keep exactly these **two active context files**:

```text
HETEROES_LLM_MASTER.md
  stable design, protocol, numerical contract, scope, ownership, roadmap, defense material

HETEROES_LLM_STATUS.md
  current machines/environments, verified experiments/results, artifacts, blockers, next action
```

`TODO.md` (repo root, added 05/10/2026 by the project owner) is a short list of code-level clean-up items only. It is not a context file: no status, no evidence, no roadmap.

Do **not** create a new long-term handoff document after every chat. Update these two files and rely on Git history for revisions. Old `Master Proposal v3`, `Implementation Roadmap v3`, `Learning Guide v3`, prior Chat Handoff and Progress Summary are archive/read-only.

For a future chat, upload/provide these two files first. If code-level work resumes, also provide the latest relevant code/probe file(s), especially the production `NoiseEngine` once created.
