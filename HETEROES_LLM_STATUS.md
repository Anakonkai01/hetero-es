# HeteroES-LLM — Status

**Last updated:** 08/10/2026, morning (the learning experiment on the runtime, see 0.0000000; earlier, 07/10 evening: G7: CUDA noise engine and the restore trade-off, see 0.00000; earlier that day: O8, FP32 evaluation by default, see 0.0000; earlier that day: G6: the audit of G2 to G5 and its fixes, see 0.000; earlier that day: G4 done and G5 done, see 0.00; before it: 06/10/2026, evening, G3 done on the two physical machines, see 0.0; before it: the ledger, steps G2a to G2f, done for one coordinator process; before it: a first short learning experiment after the gate, step 9 done, the numerical gate closed for one candidate, decisions O4, eta and seed checks of 05/10; branch `feat/worker-protocol-g3`, see 0.0). Sections 0.00000, 0.0000, 0.000, 0.00 and 0.0 are the newest, newest first (where two disagree, the earlier one in the file wins); sections 1–13 were written on 30/09 and are older background.  
**Canonical design/specification:** `HETEROES_LLM_MASTER.md`  
**Purpose:** current implementation truth, verified evidence, blockers, artifacts, and the exact next action.

> **Document rule:** `MASTER` decides what the system/design should be. `STATUS` decides what is actually done now. For a new chat, read `HETEROES_LLM_MASTER.md` and then this file; older proposal/roadmap/chat-handoff files are archive only.

## 0. NEXT SESSION — START HERE

### RESUME HERE — handoff written at the end of the session of 07/10/2026 (night)

**UPDATE of 08/10/2026 (morning), read this first.** During the night of 07/10 to 08/10 the AI (full authority granted by the owner until 10:00) did the step 1 below, the learning experiment, on the new branch `feat/learning-experiment` (from `feat/audit-hardening-g6`, 11 commits, nothing pushed, **nothing reviewed by the owner**). Folder `artifacts/experiments/2026-10-07-learning-runtime/` (README first, then `PREREGISTRATION.md` and its Addendum 1). Result in one line: two 100-generation runs on the real cluster and one exploratory run give, by the criteria written in advance, **"no evidence of learning in this experiment"** (S1 and S3 true, S2 and S4 false), while the model clearly improved on the training family and the real updates are far better than random ones over many generations: the details and the reasons are in the README and in section 0.0000000 below. The steps below are renumbered by what is left; the owner's review is still the first debt.

**Read first, in this order** (about 15 minutes): the memory files of the AI (loaded by themselves), then this block, then `CLAUDE.md`, then 0.000000 to 0.0000 below (newest first), then `TODO.md` groups `g7-next` and `c1-next`. The long files (`HETEROES_LLM_MASTER.md`, the contract, ADR-002) only when a task needs them: contract sections 13 to 16 and ADR-002 "Amendments" are the newest.

**State.** Branch `feat/audit-hardening-g6` (from `feat/benchmark-g5`), everything is COMMITTED (`git status` shows only the unrelated untracked `notebooks/floating_point_testing.ipynb`), nothing is pushed (the owner pushes), **the owner has reviewed none of the work since G2** (G6 and G7, about 40 commits, were written by the AI with full authority and tests first). The 1660S repository (`~/projects/heteroes/hetero-es`) was brought to the same commit by `git bundle` (check `git log -1` on both before any two-machine run). Tests at the last commit: see the line "final test counts" at the end of this block.

**What the system is now.** A coordinator and pull workers over HTTP on two machines (RTX 5070 Ti with the coordinator, GTX 1660 SUPER, direct cable `10.10.10.1` and `10.10.10.2`), a SQLite ledger, full synchronization of the weights, dispatch policies B1 (waves), B2 (quotas), B3 (greedy), B4 (`GreedyTail`: tail-aware), restart of the coordinator, heartbeat, a failure campaign passed on the real machines (G6). The evaluation is FP32 (O8) with chunk 16 by default. Two noise engines: the CPU one (the default, manifest v1, any machine) and the CUDA one (`--noise-engine cuda`, equal on the two GPUs, needs a GPU in the coordinator too). Two long workloads (`--workload cot_l3_q32`, `cot_l3_q64`) besides the 16 prompts of the contract (`arith16`, the default). Best measured configuration: CUDA engine, `cot_l3_q64`, chunk 64, B4x2 or B3x2: a generation of 24 candidates in 90 s, the cluster 1.19 times faster than the 5070 Ti alone (STATUS 0.000000, `artifacts/experiments/2026-10-07-g7-bigchunk/README.md`).

**Machines and environment** (do not rediscover): the 5070 Ti side runs in the conda env `heteroes-match` (`~/miniforge3/envs/heteroes-match/bin/python`, torch 2.13.0+cu132, transformers 5.17.0, Python 3.12; always `PYTHONPATH=src`); the env `ai` has an older torch: do not use it for two-machine evidence. The 1660S: `ssh anakonkai@heteroes-worker-1660s` (an SSH key is installed; Tailscale name) or `anakonkai@10.10.10.2` over the cable; `~/projects/heteroes/.venv/bin/python` (Python 3.14.4, torch 2.13.0+cu132). The pinned model snapshot is in the Hugging Face cache on both (`~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775`). Code to the 1660S: `git bundle create /tmp/x.bundle <old>..<branch>`, `scp`, then on the 1660S `git fetch /tmp/x.bundle <branch>:refs/heads/incoming && git merge --ff-only incoming`. The sudo password the owner gave for both machines is NOT stored anywhere (ask again if a task needs sudo; use it from the environment or stdin only). Never `pkill -f` or `pgrep -f` with a pattern that appears in your own command line (use the `[x]yz` trick); a foreground `sleep N; command` is blocked by the harness: run a loop with `until`, in the background for long waits.

**Commands that reproduce the main evidence** (from the repository root, `PYTHONPATH=src`, the `heteroes-match` python):
- tests: `HETEROES_QWEN_PINNED_PATH=$SNAP HETEROES_QWEN_PATH=$SNAP pytest tests` (with `HETEROES_E2E=1` also the three end-to-end cases, about 3 minutes);
- the cluster benchmark: `bash artifacts/experiments/2026-10-07-g7-bigchunk/run_campaign.sh 3` (about 2.5 hours, both machines on the same commit and free), summaries with `scripts/summarize_benchmark.py <dir> --baseline B0` and `summarize_workers.py` in the folder;
- the cross-GPU check of the CUDA engine on a real model: `artifacts/experiments/2026-10-07-g7-restore-tradeoff/cuda_engine_crossgpu.py` on both machines (compare the JSON files: every hash and the fingerprint must be equal); the exactness of a chunk: `chunk_probe_cot.py` and `compare_chunk_probe.py`; `rng_portability.py` and `bench_calls.py` for the thread-mapping study.

**Decisions taken** (contract section 11): O1 to O8 are all decided (O8 = FP32 evaluation by default); no O-decision is open. Choices of the AI that the owner should confirm when reviewing: the CUDA engine as an OPTION and not the default (the CPU engine runs without a GPU in the coordinator); the call size 22,528; the manifest extension (a recipe may name `workload.name`, and the CUDA engine value of `noise.engine_version`) that leaves every v1 hash unchanged; the restore stays the snapshot restore (the arithmetic revert was measured and rejected).

**What to do next, in order** (the AI proposes, the owner decides; each step: plan, tests first, scratch copy for mutation checks, evidence folder with a README that says what it does NOT show):
1. **[DONE the night of 07/10 to 08/10, see 0.0000000: runs A, B, C]** A learning experiment on the runtime (the plan that follows is what was done, with the deviations written in the README): the CUDA engine, `cot_l3_q64` at chunk 64 for training, held-out questions of the same family AND of another (levels 1 and 2, other seeds of the generator) before and after, a control step of `-alpha` from the same parent and noise (as in `artifacts/experiments/2026-10-06-learning-pilot/`, whose criteria were written BEFORE the runs: do the same), alpha 1e-3 as in the pilot (3e-3 made the model worse), sigma 1e-3 and smaller, N = 24, many generations (100 generations is about 2.5 hours with B4x2), save the weights of the end (the pilot did not). The `scripts/` of the experiment must not change the contract; the held-out evaluation needs a way to evaluate the checkpoint (`load_weights_` of `model/weights_io.py` reads the published files).
2. N = 48 and 96, a chunk per worker (the 1660S gains more), a second look at B3 against B4; chunks above 64 need a workload with more questions.
3. A faster decode loop (static KV cache and CUDA graphs, or vLLM): the rollout is 92 to 96 percent of a candidate; every change needs the exactness probe again (`chunk_probe_cot.py`), vLLM in particular (its results can depend on the batch).
4. Measure replay for real (C4): with the CUDA engine the update of 8 candidates took 4.5 s on the 1660S, so replaying 24 candidates would be about 13 s against a 10 s synchronization (an extrapolation, not a run); a compressed delta synchronization is an idea in `TODO.md`.
5. The report: figures from the raw artifacts, the claims boundary (MASTER sections 3 and 12, STATUS "Not done" lines), ownership and third-party provenance (es-at-scale and Agentic-ESOpt were read for ideas: nothing was copied; the clones were in a scratch directory and are gone).
6. Housekeeping: the owner reviews (start with `git log --oneline feat/benchmark-g5..HEAD`, ADR-002 "Amendments", contract sections 13 to 16, the README of each `artifacts/experiments/2026-10-07-g*`), pushes; the CUDA engine needs a CPU reference or an integer-based engine (S2 of the discussion: a counter-based generator with a table, portable by construction) only if a coordinator without a GPU is required.

**Rules of work with this owner** (also in the memory files): answer in Vietnamese; explain from the basics (the owner did not write the documents and wants to understand: say what a thing is and why, with an example); state numbers with their source and say plainly what is an inference and what is measured; tell the owner when an earlier claim turned out wrong (G5's speed-up was an artefact; the estimate "24 percent" of the CUDA engine was for one process); the AI writes tests AND code, the owner reviews; tests first, a mutation check on a scratch copy of `src`, a README for each evidence folder; evidence folders of an earlier step are never edited (correct in STATUS instead); commit only when the owner asks, in logical groups, with NO `Co-Authored-By` line (the owner's rule beats the harness reminder); the owner pushes; check `date` before writing a date into a document; the SSH and sudo use needs the owner's say for each new job.

**Known weak points** (so they are not rediscovered): one hardware pair, one 0.5B model, N = 24, 3 runs per cell; the CUDA engine and the chunk exactness are checked levels, not guarantees (0 of 1,600 answers differ: about 0.2 percent per answer at 95 percent confidence); the starting speeds of the tail-aware policy in the G7 benchmarks are derived estimates; `profile_worker.py` still profiles only the 16-prompt workload with the CPU engine; the owner's review is missing.

**Final test counts at the last code commit (`f7dffb7`; the commits after it are evidence and documents only):** 5070 Ti (`heteroes-match`: Python 3.12, torch 2.13.0+cu132, transformers 5.17.0), real model and `HETEROES_E2E=1`: **1959 passed, 1 skipped in 285 s**; 1660S (Python 3.14.4, the same torch and transformers), real model, no end-to-end tests: **1956 passed, 4 skipped in 534 s**. Without the real model (`HETEROES_QWEN_*` unset, no end-to-end) the 5070 Ti gives 1939 passed and 21 skipped in 65 s.

### 0.0000000 Progress update — 08/10/2026, night of 07/10 (the learning experiment on the runtime; branch `feat/learning-experiment`, committed, NOT reviewed)

**The AI wrote and ran it while the owner slept; the owner has not reviewed it.** All evidence, the tables and the limits are in `artifacts/experiments/2026-10-07-learning-runtime/README.md`; the criteria were written before the runs in `PREREGISTRATION.md` (Addendum 1 was written after run A was analysed, before run C).

- **What ran.** Run A (`lrtA`) and run B (`lrtB`, other noise): the whole runtime (coordinator, two worker processes on the 5070 Ti and one on the 1660S, tail-aware policy, CUDA engine, FP32, chunk 64), workload `cot_l3_q64`, N = 24, sigma 1e-3, alpha 1e-3, 100 generations each (2.6 and 3.0 hours; 91 s per generation in A). Run C (`lrtC`, EXPLORATORY): alpha 5e-4, 60 generations, 5070 Ti only. Weights of every 5th generation were kept; an offline analysis rebuilt every parent from the ledger's update records and checked it against the stored hashes (**all 52 segments of A, B and C matched**), and measured parent, parent+ (the real step) and the control parent- (the same step with -alpha) on the training questions at every generation, and three held-out sets of 128 questions (the training family H3, and two other families H1 and H2) at every 5th.
- **Verdict by the rules written in advance: A, B and C all "no evidence of learning in this experiment".** S1 (H3 +8 questions) and S3 (train +0.10) true; S2 (the real step beats the anti-step in at least 70 percent of the generations) false (A 44 of 100, B 46 of 100, C 30 of 60); S4 (H1 and H2 not more than 8 questions lower) false because of H2 (116 -> 99, 88 and 100 of 128). That verdict stands.
- **What the same data say beyond the criteria** (post hoc or exploratory, labelled so in the README): H3 42 -> 112 (A), 89 (B, peak 108 at generation 20), 104 (C); training 19 -> 60 of 64; the training score saturates at 59 to 62 of 64 from generation ~30 and a third of the later generations are ties, so S2 could not be met; between generations 10 and 30 the real step beat the anti-step 15 to 2 (A), 14 to 4 (B), 12 to 6 (C); **50 steps with shuffled coefficients from checkpoint 50 destroy the training score (10 to 47 of 64 in A, 28 to 41 in B) while the real steps keep 60**; the drop of H2 is as large under random steps as under the real ones (drift of a saturated model, 2 walks per run); part of the gain is "answer shorter" (36 of 64 base replies hit the 256-token limit with no `Answer:` line; every perturbed copy scores about 0.72) and the model stops writing the `Answer:` line in B, so S5 is undefined there.
- **Incident.** The 1660S became unreachable twice under load (about 00:45, generation 91 of run A; about 02:41, generation 49 of run B); the owner restarted it once; the cause is unknown (no log looked at). The runs went on with the 5070 Ti alone and the results do not depend on it (the ledger has each result once, the replay reproduces every hash). The worker logs of the 1660S were lost in both runs (the copy back failed), so the share of the 1660S (375 of 2,400 candidates in A and 304 in B) is derived, not logged.
- **Code and tests.** `scripts/cluster_runner.py` got `--alpha` and `--sigma` (default 1e-3: nothing changes for the other scripts; 2 tests); the experiment folder has `learnlib.py` (held-out sets, checkpoint keeper, verdict arithmetic; 36 tests in `tests/experiments/`, mutation check of 19 faults: 18 caught, 1 equivalent), `run_learning.py` (starts the processes, keeps the checkpoints, restarts what dies), `analyze_run.py`, `random_walk_control.py`, `summarize_analysis.py`. The package (`src/`) is untouched. `run_learning.py` and `analyze_run.py` are not unit-tested (the runs exercised them; a 5-generation smoke run that was not kept came first). The full test suite was re-run after all changes on the 5070 Ti (`heteroes-match`, real model, without `HETEROES_E2E`): **1994 passed, 4 skipped in 118 s**; not re-run on the 1660S (it was down).
- **Not done / limits.** One model, one family, one hardware pair, N = 24, 64 training questions, two seed families plus one exploratory alpha; no other sigma; no early stopping on held-out; no comparison with another algorithm. Next, by the owner's decision: a criterion that handles ties and the cumulative effect (the random-walk control as a preregistered test), a larger training set or a workload that is not limited by the 256-token cut, early stopping on held-out accuracy, a smaller sigma with a larger N; see `TODO.md`, group `learning-runtime-next`.

### 0.000000 Progress update — 07/10/2026, night (G7 continued: what limits the rollout, and a benchmark with a bigger chunk; committed)

**The AI wrote and ran it; the owner has not reviewed it; committed (the commits after `f7dffb7`).** Evidence: `artifacts/experiments/2026-10-07-g7-restore-tradeoff/` (section 6, `rollout-scaling-*.json`, `chunkprobe-*.json`) and `artifacts/experiments/2026-10-07-g7-bigchunk/` (README).

- **The rollout is 92 to 96 percent of a candidate and its decode loop is limited by the latency of each step**, not by the arithmetic: seconds per question fall almost inversely with the number of prompts per `generate()` call (chunk 16, 32, 64: 0.142, 0.087, 0.067 s on the 5070 Ti; 0.929, 0.489, 0.283 s on the 1660S).
- **Chunks 32 and 64 are exact** for the long workload in FP32: 0 of 1,600 answers differ from chunk 16 (the parent and 24 perturbed candidates, both GPUs, and between the GPUs). A checked level (about 0.2 percent per answer at 95 percent), not a guarantee.
- **New workload `cot_l3_q64`** (64 questions, the first 32 are those of `cot_l3_q32`), selectable like the other (`--workload cot_l3_q64`); 1939 tests pass.
- **The benchmark (21 runs, N = 24, 4 generations, 3 runs per cell, CUDA engine):** with the same 32 questions a chunk of 32 instead of 16 makes a generation 31 to 37 percent shorter (B0x2 69.0 s, B3x2 65.7 s, B4x2 61.9 s; speed-up of B4x2 over B0x2 1.116 +- 0.018). With 64 questions at chunk 64: **B0 107.6 s, B0x2 108.5 s (the second process gives nothing), B3x2 90.6 s (1.188 +- 0.015 over B0), B4x2 90.2 s (1.194 +- 0.012)**, 17.0 questions evaluated per second against 8.4 before, at the same time per generation. The 1660S did 16 of 96 candidates (a candidate takes it 4.3 times as long as the 5070 Ti, it was 7.5 times at chunk 16); the ceiling of any scheduling is 1.23, tail-aware reaches 1.194. The best configuration is 42 percent shorter than the best one before G7 (107.5 s to 61.9 s, 32 questions). All runs of a configuration ended with the same rewards and weights hash.
- **Not done:** a chunk per worker; chunks above 64; N other than 24; a learning experiment (the next step); static KV cache, CUDA graphs or vLLM for the decode loop.

### 0.00000 Progress update — 07/10/2026, evening (G7: a longer workload, the restore trade-off, and a CUDA noise engine that is the same on the two GPUs; committed, not reviewed)

Everything is in `artifacts/experiments/2026-10-07-g7-restore-tradeoff/` (README with the tables) and contract section 16. **The AI wrote and ran it; the owner has not reviewed it; nothing is committed; the engine is NOT in the runtime yet.**

- **Longer workload** (`cot_workload.py`): arithmetic with step-by-step reasoning, up to 256 tokens, level 3 (a word problem): accuracy 0.281, rollout 4.4 s on the 5070 Ti and 29.8 s on the 1660S for 32 questions (27 times the 16-prompt workload); the accuracy and the tokens are the same on both GPUs in FP32.
- **Noise source and way back, 2 x 2, 24 candidates, both GPUs.** CPU canonical noise or GPU `torch.Generator` noise; snapshot restore or restore by arithmetic. Outside the rollout a candidate costs 17 percent (5070 Ti) and 12 percent (1660S) with the runtime's way (CPU noise + snapshot) and 4 and 2 percent with GPU noise + snapshot. The arithmetic way back is not exact (25 percent of the elements differ after 24 candidates, growing like sqrt(k)) and with CPU noise it is slower than the snapshot (0.73 s against 0.14 s). The native GPU noise differs between the two GPUs (drift counts differ, one reward changed); the canonical noise gives identical counts on both.
- **Native GPU noise is portable up to 22,528 elements per call** (the thread count of the 1660S): equal hashes up to 22,528, different from 22,529, as the reading of PyTorch's launch policy predicts.
- **CUDA noise engine** (`noise/cuda_engine.py`, `es/cuda_ops.py`, S1 of the discussion): sequences of calls of 22,528 elements; on the real model the hashes of all weights after perturbations, a restore and an update, and the noise fingerprint are equal on the 5070 Ti and the 1660S. Whole-model perturbation 0.08 s and 0.58 s (CPU engine 0.73 s and 3.67 s), update of 8 candidates 0.64 s (CPU engine 2.4 s). 72 tests (5070 Ti), 49 (1660S, the engine's). The first version was only 2.4 times faster than the CPU because of launch overhead; fixed with a larger call and `normal_` on views.
- **What it does to a generation (an ESTIMATE, `simulate_generation.py`)**: with the CUDA engine a generation of the 5070 Ti alone is about 24 percent shorter (123 s to 93 s at N = 24); the 1660S adds 9 to 14 percent with tail-aware dispatch from N = 24 up and loses with greedy dispatch at N = 8 and, with the CUDA engine, at N = 24. A candidate of the long workload takes 30 s on the 1660S against 4 to 5 s: the long workload does not make the slow GPU relatively better, it only spreads its fixed costs.
- **Integrated afterwards (same evening, committed in `9548872` and earlier commits of the branch).** The CUDA engine and the long workload are choices of the recipe (`Recipe.engine_version`, `Recipe.workload_name`; CPU-engine and 16-prompt recipes keep their documents and hashes); the executor perturbs and the coordinator updates with the engine of the recipe; the worker builds its recipe from the job and runs the engine's self-test; scripts take `--noise-engine {cpu,cuda}` and `--workload {arith16,cot_l3_q32}`; the end-to-end test compares coordinator + 2 worker processes with the single-process reference bit for bit for the CUDA engine with the long workload too. `pytest tests` with the real model: 1953 passed, 3 skipped (5070 Ti); the three end-to-end cases passed (164 s). Written tests-first for the manifest, the workload, the executor, the coordinator and the loading.
- **The cluster benchmark** (`artifacts/experiments/2026-10-07-g7-cluster-benchmark/`, README): the long workload, N = 24, 4 generations, 3 runs per cell, the two machines. T of a generation (s, steady state): CPU engine B0x2 107.5 (+-1.3), B3x2 107.4 (+-13.3), B4x2 101.2 (+-5.8); **CUDA engine B0x2 99.5 (+-0.2), B3x2 104.3 (+-1.5), B4x2 90.9 (+-0.2)**. With the CUDA engine and tail-aware dispatch the cluster is 1.094 +- 0.004 times faster than the 5070 Ti alone (1.024 in G6), greedy dispatch is 0.954 +- 0.014 (slower than the 5070 Ti alone); the best configuration is 15.4 percent shorter than the best one before G7. The 1660S evaluated 9 to 13 of the 96 candidates of a run. In each engine all 9 runs ended with the same rewards and weights hash (identical on the two GPUs). The estimate that said "24 percent shorter" was for one worker process; against two processes on the 5070 Ti the CUDA engine gains 7.4 to 10.2 percent.
- **Not done:** N other than 24, more runs per cell, a profile of the long workload (`profile_worker.py` still profiles the 16-prompt workload with the CPU engine), a CPU fallback for a coordinator without a CUDA GPU, the check of the torch and CUDA versions at admission, a learning experiment (the effect of the drift of the arithmetic way back over thousands of candidates is extrapolated, not measured; whether the weights move usefully over many generations is not analysed); one pair of GPUs, one software stack. See `TODO.md`, group `g7-next`.

### 0.0000 Progress update — 07/10/2026, afternoon (O8 decided and implemented: the evaluation is FP32 by default; committed)

The owner decided O8 (FP32 as the default evaluation) and asked for it to be done. **The AI wrote the change and the tests; the owner has not reviewed it; nothing is committed.**

- **What changed.** `Recipe.eval_dtype` defaults to `float32` (`DEFAULT_EVAL_DTYPE`); `build_recipe` and the `--eval-dtype` of `run_coordinator.py`, `profile_worker.py` and `cluster_runner.py` default to it; `eval.precision.default_chunk` gives the exact prompts per `generate()` call (FP32: 16, FP16: 1) and `CandidateExecutor`, `run_worker.py`, `run_benchmark.py` and `failure_campaign.py` use it when `--chunk` is not given (an explicit `--chunk` still wins). `run_one_candidate.py` and the reading of the format-1 records in `compare_candidate_records.py` say `eval_dtype="float16"` on purpose: they describe the FP16 evaluation of the earlier evidence.
- **No recorded hash changed.** The recipe DOCUMENT is the same as in G6: an FP16 recipe leaves the key out (a document without the key still means FP16, `LEGACY_EVAL_DTYPE`) and keeps the v1 hash `1604737e...`; an FP32 recipe writes `eval_dtype` and has the hash `efc1ff67...` that the 150 log lines of the G6 FP32 benchmark recorded (a test pins it: evidence of real runs, not a value made by this code). Only what a recipe built without saying the precision IS has changed.
- **Tests.** 30 tests turned red at the first run, all of them because they assumed the FP16 default (the toy-model helpers of `test_executor.py`, `test_worker_runtime.py`, `test_coordinator.py` and the manifest and loading tests that pin the v1 hash); the helpers now say `eval_dtype="float16"` explicitly (those tests are about the machinery, the FP32 path has its own tests). Five tests were added (default is FP32 and its hash is the one of the G6 runs; a document without the key reads as FP16; the default chunk of each precision; the executor takes it from the recipe and an explicit chunk wins; the real model's default recipe). `pytest tests`: **5070 Ti (`heteroes-match`, real model, `HETEROES_E2E=1`): 1820 passed, 1 skipped in 204 s** (the two end-to-end tests, which start a coordinator and workers with the defaults, are in it); **1660S (Python 3.14.4, real model, no end-to-end tests): 1818 passed, 3 skipped in 537 s**, on a copy of the code under `/tmp` made from the same commit plus these files (the repository there was not touched; the copy was deleted). Mutation check on a scratch copy (7 faults: default dtype, the legacy reading of a missing key, the rule that leaves FP16 out of the document, the two numbers of the chunk table, the executor ignoring the table, a wrong `None` test): 7 of 7 caught.
- **Not done.** The profiles and the benchmark plans of G4/G5 are FP16 (their READMEs say so) and `run_benchmark.py` looks a profile up by chunk, so it needs a new FP32 profile to be used with the defaults; no run on the physical two-machine cluster was repeated with the new defaults (the G6 FP32 benchmark already ran with exactly this configuration, `--eval-dtype float32 --chunk 16`; the defaults only make it the one you get without flags). Documents updated: contract sections 11 (O8 decided) and 15, `CLAUDE.md`, `TODO.md` (`c1-next`).

### 0.000 Progress update — 07/10/2026, later (G6: an audit of G2 to G5 and what it led to; branch `feat/audit-hardening-g6`, from `feat/benchmark-g5`)

Branch `feat/audit-hardening-g6` (from `feat/benchmark-g5` at `75a328e`). Nothing was pushed. The owner asked for "a deep audit of every G phase, its bottlenecks and weaknesses, and a complete plan of improvements", then gave the AI full authority to carry it out and to review afterwards;
the AI wrote tests and code, worked on the branch (not on scratch copies as before), and made the commits at the end (no `Co-Authored-By`, the owner's rule; the sudo password the owner gave was used from the command line only and is in no file). **The owner has not reviewed any of this yet.**

**What the audit found** (three read-only audits of G2, G3 and G4/G5; each point is a fact checked in the code or in the artifacts, and the fix is in the commit list below):

| finding | where | what was done |
|---|---|---|
| The G5 headline included generation 0, where the remote worker does not synchronize; steady state at N = 24: B3 221.6 s against B0 221.3 s (ClusterBenefit 0.999, not 1.035); at N = 8 B3 was 1.058, which reverses the prediction "not beneficial". Three repeats, no interval. | `summarize_benchmark.py`, G5 README | steady-state first, Student-t intervals over runs (`benchmark_stats.py`). **The G5 claim "B3 is 3.5 percent faster at N = 24" does not hold; the README of G5 is evidence and was not edited.** |
| The admission key check could not fire (the expected key was built from the candidate's own profile). | `predict_admission.py` | `expected_key_from_reference`; reason `SOFTWARE_MISMATCH`. |
| "Bit-identical on both machines" and "0 differences in 264 evaluations" were weaker than they sounded (only 17 to 53 distinct states, other torch and transformers on the two machines). | G3/G4/G5 READMEs | the cross-GPU study below. |
| The CPU noise was 77 percent of a generation (3.7 s per candidate, and the same again inside the update). | `noise/engine.py`, `es/update.py` | ordered thread pool, bits unchanged. |
| No restart of the coordinator, a worker that died on an unexpected exception held its lease for 600 s, a B1/B2 generation with a dead worker waited for ever, a restore mismatch reported late escaped the quarantine, a database lock was a 500, lease replies lost, rewards lost with a transport error, a race at every generation boundary (a lease for the NEW parent given to a worker that had read the OLD job), weights published and never deleted, an HTTP server without timeouts, a token that failed silently. | `ledger.py`, `coordinator.py`, `worker*.py`, `http_transport.py`, `dispatch.py` | ADR-002 "Amendments" lists the ten changes, each with tests written first. |

**Speed.** On the real model (5070 Ti, 8 candidates; every weights hash identical to the serial code): perturbation 3.69 s -> 0.75 s; update 44.9 s -> 2.4 s with 16 threads (the widening of the noise to FP32 was done on the CPU, single-threaded: moving it to the device was worth as much as the threads). N = 24, the fast GPU alone, the same FP16 evaluation as G5: **221 s -> 48.9 s per generation**; with two worker processes on the GPU 35.7 s (`artifacts/experiments/2026-10-07-g6-local-scaling/`). The 1660S: perturbation 9.2 s -> 3.7 s, candidate 17.1 s -> 11.4 s; full synchronization 21.9 s -> about 10 s (the weights are hashed once, while they arrive, instead of four times at 3.6 s each on its 2012 Xeon; the loaded model is compared with the file; `artifacts/experiments/2026-10-07-g6-profiles/`). Replaying the update on the 1660S (C4) would cost 3.7 s per candidate against a 10 s synchronization: it loses from N = 3, so it was not built.

**The cross-GPU study (`artifacts/experiments/2026-10-07-g6-cross-gpu/`, both machines on torch 2.13.0+cu132 and transformers 5.17.0).** The "chunk above 1 is inexact" and "the same candidate scores differently on the other GPU" findings of G4/G5 have one cause: the FP16 forward pass rounds differently with padding and on another kernel, and the greedy answer flips at exact ties of the scores (margins 0 to 0.09 on scores of 16 to 32). Same counts with the old and the new software stack. 120 candidates x 16 prompts on both GPUs: **FP16: 33 candidates (27.5 percent) have a different answer text on the other GPU (36 of 1,920 prompts), 1 candidate a different reward** (seed 43, 0.25 against 0.1875); **FP32 forward pass from the same FP16 weights: 0 of 1,920 prompts differ, 0 rewards**. In FP32 every padded-batch comparison also agrees (0 of 1,584, against 25 of 1,056 in FP16), so batching becomes exact: the safe chunk is 16 and the evaluation of the 16 prompts takes 0.16 s instead of 0.79 s (5 times faster). It is an OPTION of the recipe (`Recipe.eval_dtype`, absent = FP16, so every v1 hash is unchanged; contract section 15). **The default stays FP16 until the owner decides (O8).** The price is about 2 GB of GPU memory per worker and results that are not bit-comparable with all the earlier FP16 evidence.

**Benchmark on the two machines after G6** (both on torch 2.13.0+cu132 and transformers 5.17.0, the direct cable, N = 24 candidates, 4 generations per run, steady state = generations 1 to 3, 95 percent Student-t intervals over runs; raw logs, summaries and READMEs in `artifacts/experiments/2026-10-07-g6-benchmark-fp32/`, `-fp16/`, `-fp32-n96/`, `2026-10-07-g6-local-scaling*/`):

| evaluation | condition | T of a generation (s) | speed-up over the baseline | repeats |
|---|---|---|---|---|
| FP32, chunk 16 | B0 (5070 Ti, 1 process) | 35.9 +- 0.2 | | 5 |
| FP32, chunk 16 | **B0x2 (5070 Ti, 2 processes), baseline** | **29.5 +- 0.2** | 1.000 | 5 |
| FP32, chunk 16 | B3x2 (+ the 1660S, greedy) | 29.6 +- 0.4 | 0.995 +- 0.016 | 5 |
| FP32, chunk 16 | B4x2 (+ the 1660S, tail-aware) | 28.8 +- 0.6 | **1.024 +- 0.023** | 5 |
| FP16, chunk 1 (as G5) | B0 (baseline) | 48.3 +- 0.7 | 1.000 | 3 |
| FP16, chunk 1 | B3 (+ the 1660S, greedy) | 51.3 +- 1.4 | **0.941 +- 0.030** | 3 |
| FP16, chunk 1 | B4 (+ the 1660S, tail-aware) | 45.5 +- 1.8 | **1.060 +- 0.046** | 3 |

What the evidence supports (and what it does not), against the claims of MASTER:

- **C2 (execution policy).** With a GPU 5 to 10 times slower in the pool, plain greedy dispatch (B3) makes the cluster SLOWER than the fast GPU alone (FP16: 0.941 +- 0.030), because the generation waits for the slow worker at its end; the tail-aware policy (B4, `GreedyTail`) gets +6 percent in FP16 and +2.4 percent over the best single machine in FP32. That is the one scheduling result with an interval that excludes "no effect". It is a gain of a few percent, not a multiple: a GPU that needs 4.9 s per candidate where the other needs 1.0 s is 20 percent of its capacity at best, and its fixed synchronization of 10 s per generation (8.5 s of it the gigabit link) eats most of that at N = 24. The G5 statement that B3 was 3.5 percent faster than B0 at N = 24 was an artefact of generation 0.
- **C1 (admission).** The profile now measures the cost of the update at several N with residuals, the gate compares the candidate with the reference worker (hardware may differ, software and recipe may not), and an FP32 profile with the safe chunk 16 exists for both GPUs. The old prediction experiment (H0, admission against forced admission) was not repeated: with the evidence above the admission question for this pair is "admit it with the tail-aware policy or not at all", and its benefit is 0 to 6 percent.
- **C4 (canonical state, synchronization against replay).** Full synchronization is 10 s on the 1660S (transfer-bound); replay costs 3.7 s of CPU noise per candidate on that CPU, so it loses from N = 3 (arithmetic from the profile, not a run). A compressed delta (an idea, not measured) is in `TODO.md`.
- **C3 (correctness under failure).** The campaign that G3 listed as not done was run on the two real machines (below): killing a worker while it holds a candidate, stopping it past its lease, cutting the link (8 s; 80 s; 3 s into a download), killing the coordinator in the middle of a generation and starting it again with `--resume`: every run ended with the weights of the undisturbed run, with one result per candidate. One run per scenario.
- **Reproducibility.** FP32: all 20 runs of the benchmark (and the 6 local ones per setting) ended with identical rewards and weights hashes whoever evaluated which candidate; FP16: 2 of the 6 runs that used the 1660S ended with other weights, because candidate 13 of generation 2 scored 0.3125 on the 1660S and 0.25 on the 5070 Ti.
- **Against G5:** the same N = 24 generation took 221 s; it takes 29 to 36 s now (7 times faster), 48 s with the unchanged FP16 evaluation.


**Failures on the two real machines** (`scripts/failure_campaign.py`; evidence in `artifacts/experiments/2026-10-07-g6-failure-campaign/` and the four `-cut-link` variants beside it, each README says what it does and does not show; N = 8, 3 generations, FP32 chunk 16, lease 20 s; every scenario passes if the experiment ends with the exact final weights of the undisturbed run, `3577eadc...`):

- `kill-worker`: `kill -9` of the 1660S worker 2 s after the ledger showed it holding candidate `g2/c7`; the lease ran out, the 5070 Ti took it (attempt 2), a new 1660S process with the same worker id rejoined and synchronized. **Passed.**
- `pause-worker`: `SIGSTOP` for 35 s (lease 20 s) then `SIGCONT`: the candidate was retaken by the 5070 Ti, the late result of the 1660S was REFUSED as stale, the worker carried on. **Passed.**
- `cut-link` (8 s): packets from the 1660S dropped during a download; TCP stalled and resumed, no error. **Passed**, but this did not exercise the resumable download. Cut for 80 s (twice, once 3 s into a download): the worker timed out, the experiment ran on with the 5070 Ti alone, the worker rejoined and synchronized to the current weights. **Passed.** With N = 32, a 15 s cut 3 s into a download and an HTTP timeout of 8 s: **the download broke off, kept 325,058,560 bytes, and resumed from that byte** (the next sync event: `resumed_from_bytes` 325058560, `downloaded_bytes` 663006976, hash checked). **Passed.**
- `kill-coordinator`: `kill -9` with 12 results committed (generation 0 complete, 4 of 8 of generation 1), started again with `--resume` 5 s later: `recovered` (`resume_generation`), `generation_resumed`, generations 1 and 2 done, both workers had logged transport errors and kept going. **Passed.**

Limits: one run per scenario; the coordinator was not killed between the write-ahead record and the update, or between the mark and the publication, on the real machines (the tests do that with two coordinator objects on the same files); no kill in the middle of a SQLite transaction; no power cut.


**Tests and mutation checks.** `pytest tests` on the final commit with the real model: **5070 Ti (`heteroes-match`: Python 3.12.14, torch 2.13.0+cu132, transformers 5.17.0, NumPy 2.5.3), `HETEROES_E2E=1`: 1815 passed, 1 skipped (a test of the `::1` address) in 217 s; 1660S (Python 3.14.4, the same torch and transformers, NumPy 2.5.2), without the end-to-end tests: 1813 passed, 3 skipped in 533 s** (before G6: 1469 on the 5070 Ti in the `ai` environment, 1365 on the 1660S). Without the real model and on the `ai` environment 1797 passed and 19 skipped. About 340 tests were added (1469 to 1815 with the real model and the end-to-end tests); every new behaviour had its test written first. Mutation checks on a scratch copy of `src` (a small runner in the session's scratchpad, the lists of faults are not in the repo; counts only): 93 deliberate faults in the new code (thread pool, update and perturbation batching, ledger, worker API, dispatch incl. GreedyTail, coordinator recovery, worker, HTTP, download, executor): 81 were caught at the first run; of the 12 that survived, 8 showed gaps in my tests (an unreachable cancel, a pool test that never reached the bound, the lease-time charge of a quarantined worker, the bound of the remembered request ids, the recomputed-child check of the restart, the 416 branch of the download, the fastest-of-others rule, the failure rule inside GreedyTail): new tests were written and the 8 are now caught; 4 are equivalent (`threads >= 0` because the pool refuses 0 workers itself, an `ORDER BY` on the primary key, a second `unlink` of a partial file, a guard that the policy's own bookkeeping makes redundant). Tests found real defects while they were written: the lease for the new parent at a generation boundary (it made a G3 test flaky since 06/10), a retry of a lease that was never possible, `allow_unauthenticated` not reaching the coordinator's server (caught by a test before the first two-machine run).

**Not done / not verified.** The audit of the MASTER claims (C1, C2, C4) against the new numbers is in the "what the evidence supports" lines above; no learning experiment was run on the distributed runtime; the owner has not reviewed ADR-002 and its amendments; the network set-up is still by hand; one hardware pair, one workload of 16 prompts (the rollout is 0.16 s: the CPU noise and the update, not the GPU, set the speed, so a slow GPU can add little); the FP32 result is a checked level (rule of three: at most 0.16 percent of prompts), not a guarantee.

**Next action.** (1) [O8 was decided and implemented afterwards, see 0.0000] The owner reviews the branch (start with `git log --oneline feat/benchmark-g5..HEAD`, ADR-002 "Amendments", contract sections 13 to 15, `artifacts/experiments/2026-10-07-g6-*/README.md`), then pushes. (2) A workload whose rollout is long enough for the slow GPU to matter, and learning experiments on the runtime. (3) The report: the evidence of G6 replaces the speed claims of G5.

### 0.00 Progress update — 07/10/2026 (G4 and G5 done, each in its own branch; C1 profiles, admission, B2, and two findings that change what G3 claimed)

Branches: `feat/c1-profile-g4` (G4, from `feat/worker-protocol-g3`), then `feat/benchmark-g5` (G5, from G4). Nothing was pushed. The AI wrote tests and code, no `Co-Authored-By` (the owner's rule).

- **G4 (MASTER gate of 18/10, reached on 07/10).** `src/heteroes/profile.py` (chunk probe, safe chunk, key of a profile), `src/heteroes/admission.py` (hard capability gate with reason codes, prediction of the time of a generation, `decide`), B2 `StaticProportional` + `proportional_quotas` + `AdmittedOnly` in `src/heteroes/dispatch.py`, prompt `chunk` in `evaluate_model`/`CandidateExecutor`, scripts `profile_worker.py`, `serve_weights.py`, `predict_admission.py`, `run_benchmark.py`, `summarize_benchmark.py`. Evidence: `artifacts/experiments/2026-10-07-g4-profiles/` (two real profiles, the predictions written before the runs) and `2026-10-07-g4-admission-b2/` (B0/B2/B3/H0 at N = 8 and 24, one run each; README with the tables). Tests: 1469 passed on the 5070 Ti with the real model and `HETEROES_E2E=1` (about 7 minutes); the new tests are in `tests/c1/` and `tests/ledger/test_dispatch_b2.py`; mutation checks on scratch copies: dispatch 15/15 (one mutant text did not match), profile 11/11, admission 25/25 (the first profile probe: 15/17, both alive mutants equivalent).
- **Admission against forced admission (G4).** N = 8: decision "eligible but not beneficial"; forced admission gave +2.6 percent (below the 5 percent threshold, but the predicted sign was wrong). N = 24: decision "admitted" (predicted +7.0 percent); measured +7.5 percent (ClusterBenefit 1.081, DeltaT 17.1 s). B2 was predicted worse than B3 and was (0.92 and 1.06 against 1.03 and 1.08). Absolute times are over-predicted by 13 to 19 percent (update cost). One run per condition: no statistics.
- **Finding 1: the first safe-chunk probe was too weak.** With 2 perturbed candidates the 5070 Ti looked exact at chunk 16; with 32 every chunk above 1 changes some answer text on both GPUs (the run with chunk 16 changed the reward of one candidate in 24). The probe now compares 32 candidates (`--probe-candidates`). Both safe chunks are 1, so H0 and B0 are the same configuration.
- **Finding 2: the G3 claim "bit-identical rewards on both machines" held for 24 candidates, not in general.** Single-process references on each machine with the same seeds (`2026-10-07-g4-admission-b2/references/`): generation 0, candidate 21, 5070 Ti 0.25 against 1660S 0.1875, the other 23 equal. In a distributed run a candidate evaluated by the 1660S can therefore give another reward than on the 5070 Ti (it did once in the G4 N = 24 B2 run, generation 1 candidate 2, and 1 in 24 in the reference), but it did not in the 264 evaluations by the 1660S of G5 (all 24 G5 runs ended with identical weights): the rate is small and unknown. B3 assigns candidates by timing, so two B3 runs of an experiment can in principle end with different weights. The cause (kernels in FP16 on sm_75 and sm_120) is not isolated. Open decision for the owner: accept it as hardware noise, restrict an experiment to one GPU model, or look for the layer that differs.
- **G5 (MASTER gate of 25/10, reached on 07/10): `artifacts/experiments/2026-10-07-g5-benchmark/` (README with the tables).** B0, B1, B2, B3, three repeats each, N = 8 and N = 24 (24 runs, rewards and hashes identical in all). T (s): N = 8: B0 85.2, B1 127.7, B2 92.9, B3 84.3; N = 24: B0 223.8, B1 341.3, B2 216.1, B3 216.3. ClusterBenefit of B3: 1.011 (N = 8, no gain) and 1.035 (N = 24, 7.5 s, ranges do not overlap). B1 is by far the worst (0.66); B2 equals B3 at N = 24 and is worse at N = 8. The admission was right at N = 8 and a false admission at the 5 percent bar at N = 24 (predicted +8.2 percent, measured +3.5), analysed in the README. H0 was not run apart (both safe chunks are 1: H0 = B0 or B3). Not shown: statistics beyond 3 values, other GPUs, any gain from C4.
- **Where the time goes** (measured): a candidate costs 4.5 s on the 5070 Ti (3.67 s of it is CPU noise generation) and 17 s on the 1660S; the update on the coordinator is about half of T (4.4 s per candidate plus about 10 s fixed, affine fit of two runs); a generation starts for the 1660S with a 22 to 35 s synchronization. The cheapest lever is the CPU noise (parallelize the chunks, no byte changes: TODO `learning`).

### 0.0 Progress update — 06/10/2026, evening (G3 done: HTTP worker and coordinator, B1/B3 and full synchronization on the 5070 Ti and the 1660S; earlier that day the ledger G2a to G2f on the 5070 Ti; earlier, 05/10 to 06/10: the numerical gate, steps 1 to 9, closed for one candidate on both GPUs, manifest v1 frozen)

Branch `feat/perturb-restore-update`, built on `main` at `2bd2073`. Last pushed commit: `e852355` (the owner pushes; the branch is many commits ahead: check `git rev-list --count origin/feat/perturb-restore-update..HEAD`). Everything is committed except the untracked, unrelated `notebooks/floating_point_testing.ipynb`. Check `git status -sb` and `git log` again.

- **Implemented and committed:** `src/heteroes/es/perturb.py` (`perturb_parameter_`, `perturb_model_`: contract O2 = (c), every check done before the first write), `src/heteroes/es/snapshot.py` (`take_snapshot`, `diff_from_snapshot`, `restore_from_snapshot_`, `RestoreError`; bitwise comparison through an int16 view, in slabs of `slab_elements`), `src/heteroes/es/checks.py` (shared input checks), and `resolve_tensors` plus `SchemaMismatchError` in `src/heteroes/model/schema.py`. Tests: `tests/es/test_perturb.py`, `test_perturb_model.py`, `test_snapshot.py` and `tests/model/test_resolve_tensors.py`.
- **Measured (5070 Ti only; torch 2.10, NumPy 2.4.5, Python 3.12):** `pytest tests` without the two step-5 test files gives 258 passed and 3 skipped. With the real model (`HETEROES_QWEN_PINNED_PATH` and `HETEROES_QWEN_PATH` pointing at the Hugging Face snapshot of `Qwen/Qwen2.5-0.5B-Instruct@7ae55760…`) it gives 261 passed. On the real model the package's `perturb_model_` (seed 0, sigma = float32(1e-3)) gives a whole-model hash that starts with `8aa3eb9af895cb4a`, the same as the four environments of 03/10, on the GPU and also with the GPU hidden (CPU only). Perturb followed by restore gives back the original bits (SHA-256 of all weights equal). The extra GPU memory during restore stays below 256 MiB (that bound is asserted in a test; the actual peak was not recorded).
- **Mutation checks (by hand on scratch copies, not automated):** perturb 15 deliberate faults, `perturb_model_`/`resolve_tensors` 16, snapshot 14. All were caught except equivalent mutants, i.e. faults that cannot change any result: the `float(np.float32(sigma))` line (PyTorch already rounds a Python scalar to float32; the line is kept on purpose), a `zip` without `strict=True`, and a sigma pre-check that passes `0.0` (sigma is the same for every tensor, so the first write already fails). Three gaps in my own tests were found this way and closed.
- **Not verified:** none of this package code has run on the 1660S yet (restore on 6 GB is untested); the real-model hash covers seed 0 and sigma = 1e-3 only. (Predictions and reward: see step 6 below, 5070 Ti only.)
- **Step 5 (reward standardization + FP32 ES update) is implemented (05/10 evening); the numerical checks are NOT done on the 1660S.** `src/heteroes/es/update.py` (`UpdateReport`, `standardize_rewards`, `apply_es_update_`) was written by the owner against the specification tests `tests/es/test_standardize.py` and `tests/es/test_update.py`. Two mistakes found by the first test run were fixed by the owner (a misplaced parenthesis in the `changed` count and `numel` taken from the last tensor instead of the whole model). Measured on the 5070 Ti (torch 2.10, NumPy 2.4.5): `pytest tests` with the real model (env vars as in `CLAUDE.md`) gives **325 passed**. Not measured: the run without the env vars, anything on the 1660S, seeds other than 0 to 3, sigma other than 1e-3, any effect on reward or learning.
- **MASTER Gate G3 (§22.5) is met on the two physical machines (06/10, evening).** Branch `feat/worker-protocol-g3` (from `feat/perturb-restore-update`). Built: the worker protocol (`worker_api.py`, `worker.py`), the dispatch policies B3 greedy and B1 static-wave (`dispatch.py`), a stdlib HTTP coordinator server and client with token, idempotent retries and model download (`http_transport.py`), the weights file named after its SHA-256 (`model/weights_io.py`), the candidate executor with verified restore and typed failures (`executor.py`), the worker runtime with admission and full synchronization (`worker_runtime.py`), the coordinator that runs generations with the write-ahead update record and publishes the child weights (`coordinator.py`), and the scripts `run_coordinator.py`, `run_worker.py`, `reference_generations.py`, `compare_generation_runs.py`. The ledger is safe for threads (one lock; several connections to one file) with real-thread tests. Evidence: `artifacts/experiments/2026-10-06-g3-local-two-process/` (one machine, two worker processes), and the physical runs `2026-10-06-g3-two-machines-cable/` (B3) and `…-cable-wave/` (B1): coordinator and a worker on the 5070 Ti, a worker on the 1660S, HTTP over a direct gigabit cable, 8 candidates, 3 generations, every reward and every weights hash **bit-identical to the single-process reference** (13 of 13 lines EQUAL in both), the 1660S downloading the 988,065,536-byte weights twice per run (transfer 8.5 s, load 4.1 s, hash check 4.8 s each) with the hash checked before use; the recipe hash is the one of the numerical gate. Folders `…-two-machines`, `…-8c3g` (Wi-Fi, about 3 MB/s: the 1660S could not finish the download in time, so that run does not show synchronization on the 1660S) and `…-cable-attempt1-firewall-blocked` are kept as weaker or failed runs; each has a README.
- **G3: what it does NOT show.** No speedup: the distributed runs (303.6 s greedy, 450.4 s waves) were slower than the single-process references (223.4 s, 210.3 s), the coordinator's update takes about 46 s per generation and the 1660S is about 4 times slower per candidate. One run per configuration, no statistics. No failure injected on the physical machines, no restart of the coordinator. The synchronization time depends on the link. The network set-up (cable, addresses `10.10.10.1` and `10.10.10.2`, one ufw rule) is by hand and outside the repository. See `TODO.md` group `g3-next` and the README of `2026-10-06-g3-two-machines-cable`.
- **Measured for G3:** `pytest tests` on the 5070 Ti (Python 3.12): **1368 passed, 2 skipped with the real model (about 155 s; the two skipped are the end-to-end tests that need `HETEROES_E2E=1`)** and **1352 passed, 18 skipped without it (about 50 s)**; on the 1660S (Python 3.14.4, with `hypothesis` and `simpy` installed there, real model) **1365 passed in about 10 minutes**, measured before the three test cases added at the end of the day (the two end-to-end tests were not run there); `tests/test_e2e_local.py` (`HETEROES_E2E=1`, about 5 minutes) 2 passed on the 5070 Ti. Mutation check of the G3 code by hand on a scratch copy: 70 random operator mutants of seven modules, 61 caught, 7 equivalent (`frozen=True`, wording of messages, a header the server ignores), 2 gaps found and closed by three new test cases (a NaN in the reply of `local_transport`; a cache directory whose parents do not exist). Only a sample, the script is not in the repo.
- **Access to the 1660S (06/10, evening):** the owner authorized SSH, a key and the use of the password (`sudo` too) for the set-up. An SSH key of the 5070 Ti was installed on the 1660S (`ssh-copy-id`); the password is not stored in any file. Both machines got a NetworkManager connection `heteroes-direct` on `eno1` and the 5070 Ti one narrow ufw rule (only `10.10.10.2` to 8765/tcp on `eno1`).
- **Decided 05/10:** O4 = canonical FP16 epsilon upcast to FP32 (measurements and accepted trade-off in the contract section 8; monitoring of the rounding errors is future work, `TODO.md` group `monitoring`). **Also decided 05/10:** the seeds of one update must be real integers and pairwise distinct (contract section 3); O5 (where seeds come from) is deferred to step 8. **Also decided 05/10:** eta = 1e-9 (the notebook used 1e-8); `standardize_rewards` computes in float64 and returns float32. **Not yet approved:** the report fields of `UpdateReport` (they come from what `test_update.py` expects). A comparison with how other ES code handles rewards is in `docs/numerical-contract.md` section 7.1 (read through a page summarizer, not checked word for word).
- **Mutation check of `update.py` (by hand on a scratch copy of `src`, not automated):** 27 deliberate faults, all caught except two equivalent mutants (`acc` created in FP16 but PyTorch promotes the sum to FP32; `alpha` not rounded to float32 first, PyTorch rounds the scalar anyway). A real FP16 accumulation (M02b) is caught. The first run found three gaps in my tests (counting `changed` numerically instead of by bits, an invalid `chunk_elements`, and a length mismatch of seeds and rewards, both hidden behind a silent no-op when the rewards are equal); tests for them were added and the mutants are now caught. Uncommitted files at the end of the session: `CLAUDE.md`, STATUS, `TODO.md`, the contract, `docs/architecture.md`, `update.py`, `test_standardize.py`, `test_update.py`.
- **Measured 05/10 with scratch scripts (not in the repo; the numbers are in the contract section 8):** on the real model (all 494,032,768 elements, seeds 0 to 3, sigma = float32(1e-3), NumPy 2.4.5, CPU) the cast of epsilon to FP16 changes it by 2.08e-4 in relative L2 norm; the rounding of theta' (realized perturbation versus canonical epsilon) by 5.4e-3, with 0.405% of the elements unchanged. Limits and the open question (effect on learning) are in the contract and in `TODO.md`, group `monitoring`.
- **Tests added 05/10 (specification, written by the AI):** `tests/es/test_update.py` also checks seed types (`float`, `bool`, `str`, `None` raise `TypeError`), that `[1, "1"]` is refused, that NumPy integer seeds behave like Python integers and that `[1, np.int64(1)]` is a duplicate; that an invalid `chunk_elements` or a length mismatch is rejected even when the rewards are equal; and that `changed` is counted by raw bits (a flip of -0.0 to +0.0 counts).
- **Step 6 (one candidate end to end) is done on the 5070 Ti only (05/10 night).** New: `src/heteroes/eval/workload.py` (the 16-prompt workload of the probe, `extract_integer`, exact-match reward, `workload_hash`), `src/heteroes/eval/generate.py` (`generate_answer`, `evaluate_model`), `src/heteroes/eval/candidate.py` (`run_candidate`, `model_weights_sha256`) and `scripts/run_one_candidate.py` (JSON record with environment, commit, model, generation config; refuses to overwrite a file and refuses a model directory that is not the pinned revision). Commits `f036ca6` (6a, 6b) and `30275cd` (6c). The tests were written first by the AI (with a reference implementation in a scratch copy, only to prove that they can pass); the owner approved the code before it entered the repo. Evidence: `artifacts/regression/2026-10-05-one-candidate/` (two processes, two runs each, so the same candidate ran four times). Measured: schema hash, workload hash and the whole-model hash of the perturbed weights (`8aa3eb9af895cb4a...`) equal to the earlier evidence; base outputs equal to the probe of 29/09 text for text (reward 0.25); restore bit for bit; outputs after restore equal to the base outputs; all four runs identical. The candidate (seed 0, sigma 1e-3) scores 0.3125 and changes the text of 10 of the 16 answers: one candidate and 16 prompts say nothing about learning. `pytest tests` with the real model: **404 passed** (about 107 s); without the env vars 390 passed and 14 skipped (5070 Ti). Mutation check by hand on scratch copies: 12 faults for `workload.py` (11 caught, the 12th revealed a gap that was closed), 13 for `generate.py` (all caught), 29 for `candidate.py` and the script (all caught but one equivalent mutant: reading the bits through an int16 view or as FP16 gives the same bytes). `git_dirty` is true in the JSON files: the only untracked path was an unrelated notebook (see the README of the folder).
- **Found in step 6:** the checkpoint's `generation_config.json` has `repetition_penalty` 1.1 and sampling flags; transformers reports that `temperature`, `top_p` and `top_k` are ignored when `do_sample=False`, while the repetition penalty stays in the recorded configuration (hash `05744820...`). The checkpoint is stored in bfloat16 and loaded as FP16. Records of the other machine must show the same generation config hash.
- **Step 7 (same candidate on the 1660S) is done (06/10, early morning).** The owner authorized SSH to the 1660S for this step (password login; no key was installed, nothing was saved). The unpushed commits were sent as a `git bundle` (SHA-256 checked) and `30275cd` was checked out detached on the 1660S (clean tree, same commit as the 5070 Ti run). There: `pytest tests` with the real model gives **404 passed in 471 s** (same count as the 5070 Ti, 107 s), and `scripts/run_one_candidate.py` (seed 0, sigma 1e-3, `--repeat 2`, two processes) gives records that are identical to each other. Compared with the 5070 Ti records: schema, workload, engine, chunk size, seed, sigma, model and tokenizer revision, and the three whole-model weight hashes (original `c9118c8a...`, perturbed `8aa3eb9af895cb4a...`, restored) are **equal**; the outputs of the 16 questions of the base model, of the candidate and of the restored model are **equal text for text**; rewards 0.25, 0.3125, 0.25 on both; every pair of files (each 5070 Ti file against each 1660S file) agrees. Machines: 5070 Ti (cc 12.0, Python 3.12.13, torch 2.10, NumPy 2.4.5, transformers 5.5.0) and 1660S (cc 7.5, Python 3.14.4, torch 2.13, NumPy 2.5.2, transformers 5.17.0). Same `model.safetensors` blob on both. Evidence and README: `artifacts/regression/2026-10-06-cross-machine-one-candidate/`. So the checks of the cross-machine gate (contract section 9) hold for ONE candidate on these two machines: noise and perturbed weights, restore on both, the 16 predictions, the reward. Limits: one seed, one sigma, 16 prompts, greedy decoding, two machines; not a universal guarantee.
- **Found in step 7:** the hash of the whole `generation_config` dict differs between the machines (`05744820...` and `8fb3597a...`) only because transformers 5.17 adds four keys with value `None` and stores its own version; the set values are identical. The comparison script therefore compares the SET values and shows the raw hash as information. That rule was first chosen by the AI after it saw the difference; the owner approved it on 06/10 (step 8) and it is now the rule of the manifest. The 1660S has leftovers in `/tmp` (bundle, logs, outputs), a new local branch `feat/perturb-restore-update` and a detached HEAD at `30275cd` (its old branch is untouched).
- **Step 8 (manifest v1 frozen) is done (06/10).** The owner approved the design: two layers, pin the behaviour and not the NumPy version, explicit seeds, the set values of the generation config. New (contract section 12): `src/heteroes/canonical.py` (the ONE serialization for hashes, now used by the schema hash, the workload hash and the manifest), `src/heteroes/noise/selftest.py` (noise fingerprint of five golden chunks, 13 ms on the 5070 Ti), `src/heteroes/manifest.py` (`Recipe`, `CandidateDescriptor`, `derive_seed`, `effective_generation_config`), `scripts/compare_candidate_records.py` (now in the repo; compares by recipe hash, lists measured differences), and `scripts/run_one_candidate.py` writes record format 2 (recipe, recipe hash, descriptor, noise self-test result; it refuses to run if the self-test fails). **O5 decided:** seeds are explicit data in the descriptor, range `0 <= seed < 2^53`; the coordinator chooses them, preferably with `derive_seed` (not part of the cross-machine contract); the regression keeps `[0..3]`. **O6 decided:** no NumPy version is pinned; the recipe holds the noise fingerprint and each worker runs the self-test (the version is only reported). The recipe hash built from the records of the 5070 Ti and of the 1660S is the same, `1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1`; with a NumPy version in the hash they would differ (2.4.5 and 2.5.2). `alpha` is not in the recipe (a parameter of each generation). Measured on the 5070 Ti: `pytest tests` with the real model **535 passed** (about 107 s), 521 passed and 14 skipped without the env vars. The tests were written first by the AI (in a scratch copy, with a reference implementation), approved by the owner and then copied; mutation check by hand on the scratch copy: 33 faults, all caught but one equivalent mutant (the explicit label check in `Recipe.from_dict` is also caught by the round-trip check). Pinned values in the tests (recipe hash, noise fingerprint, derived seed) were produced by this code: regression guards, not independent evidence; the five golden digests are evidence of four environments. Limits: the format-2 script has not been run on the 1660S (the evidence of 05/10 and 06/10 has format 1 and was checked offline); the self-test is not yet part of a worker admission.
- **Step 9 (clean commit, evidence, STATUS) is done (06/10): the numerical gate is closed for ONE candidate on the two machines.** Commits: `c12053d` (step 8 code and tests), `c8d8831` (the step 7 evidence), `588fa71` (documents). On the committed tree `pytest tests` with the real model gives **535 passed** (107 s, 5070 Ti). New evidence `artifacts/regression/2026-10-06-manifest-v1-5070ti/`: the first record of format 2, written by the real script at `588fa71`: the noise self-test passed (about 5 ms), the recipe hash is `1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1`, equal to the hash rebuilt offline from the format-1 records of the 5070 Ti and of the 1660S, and the comparison script reports every must-be-equal line equal against both. The weights, the 16 outputs and the rewards are the same as before (hashes `c9118c8a...`, `8aa3eb9af895cb4a...`, `c9118c8a...`; rewards 0.25, 0.3125, 0.25). The README of the step 7 folder says that the comparison script was not in the repository yet: that was true when it was written (the README is evidence and is not edited); it is in the repository since `c12053d`. What the gate does NOT cover: only one candidate (seed 0, sigma 1e-3), 16 prompts, greedy decoding, two machines; the format-2 script was run on the 5070 Ti only; `pytest tests` was not rerun on the 1660S after step 8 (404 passed there before it); the noise self-test is not part of a worker admission.
- **Short learning experiment (06/10 night, 5070 Ti only): a first positive signal, not a proof.** Folder `artifacts/experiments/2026-10-06-learning-pilot/` (README, scripts, results of every generation; criteria written before the runs). New arithmetic questions (subtraction of two 2-digit numbers, 1x2-digit and 2x2-digit products; 96 train, 96 held-out, none of the frozen 16), N = 8 candidates, sigma = 1e-3, 10 generations, each with a control step of -alpha from the same parent and noise. Results (held-out accuracy before -> after): **alpha 3e-3: 0.667 -> 0.469 (-19 questions), the model gets worse (S1 no, S2 yes 10/10, S3 no); alpha 1e-3: 0.667 -> 0.885 (+21), all three criteria met; replication of alpha 1e-3 with other seeds: 0.667 -> 0.823 (+15), S1 and S3 met but S2 NOT (the + step beat the - step in 7 of 10 generations, the threshold was 8).** By the rule fixed in advance only one of the two runs at alpha 1e-3 is a full success. The gain is not a change of format (in the replication the answers are integers only, 17 questions went from a wrong integer to the right one, 2 the other way; mostly subtraction 21 -> 31 of 32). Limits: one model, one task family, one machine, N = 8, 10 generations, one question = 1.04 points, two alphas tried and the better one singled out after seeing both, held-out from the same generator as the train questions, no comparison with another method, the final weights were not saved. Also observed: candidates score below their parent on average (0.06 to 0.11) and only 0 to 3 of 8 beat it, so sigma = 1e-3 is strong for these questions (a smaller sigma was not tried). Time: about 21 to 23 minutes per run, dominated by the CPU noise generation. The scripts are experiment scripts, not tested package code.
- **The ledger, steps G2a to G2f (06/10, 10:00 to 13:15), on the 5070 Ti only: done for one coordinator process.** MASTER §22.4 (Sprint 2) asked for a durable ledger with fake workers by 04/10; this was finished on 06/10 (two days after the MASTER date). Commits: `b8fce14` (G2a: generations and candidates), `3b78a2d` (G2b: leases, attempts, retry budget), `b1c9801` (G2c: results and failures), `8759264` (G2d: generation state, results for the update, quarantine), `c8a2f19` (G2e: system tests), `cc8f243` (G2f: coefficients and the update record), `fcb6ca7` (ADR-002). Design, alternatives and limits are in `docs/adr/ADR-002-candidate-attempt-lease-ledger.md` (a draft by Claude, pending the owner's review) and in the numerical contract §13. In short: a candidate (logical job) has attempts, each with a lease and a random token; leases expire lazily and the latest attempt may still deliver after its deadline if nobody took over; results are idempotent (the same again is acknowledged, another reward for the same attempt is refused); a failure is typed and never a reward; a failed restore quarantines the worker; the state of a generation is computed (OPEN / COMPLETE / FAILED) and only a COMPLETE one gives `(seeds, rewards)` in index order; the update record (seeds, rewards, coefficients, alpha) is written BEFORE the weights change and the child weights hash is marked after. The coefficients of the update are computed once and travel (decision O7): `apply_es_update_` was split into standardization plus `apply_coefficients_` (same bits, tested on the real model).
- **Measured for the ledger (5070 Ti, Python 3.12, NumPy 2.4.5):** `pytest tests` gives **978 passed, 14 skipped in about 30 s** without the env vars and **992 passed in 139 s** with the real model (before the ledger: 535 with the model). Mutation checks by hand on scratch copies (deliberate faults, not automated): G2a all caught but 2 equivalent (`PRAGMA foreign_keys`, closing after a failed start); G2b 45 faults, 2 equivalent survivors; G2c 46, 2 equivalent; G2d 43, all caught; G2e's own tests alone caught 36 of the same 43 (the other 7 are outside their remit: messages, type checks, other generations, SQL constraints); G2f: `GenerationRecord` 33 of 33, ledger update code 37 of 38, `apply_coefficients_` 8 of 10 (2 equivalent). The one fault no test sees is the removal of `BEGIN IMMEDIATE` (the write lock taken before reading): it needs two threads; this is reasoning, not an experiment. The tests found several gaps in themselves (mutants that stayed green) and these were closed. Random schedules: Hypothesis, 150 examples per test by default, 3,000 with `HETEROES_HYPOTHESIS=fuzz` (no failure found); exhaustive orders of small alphabets: 32,706 sequences by default, 113,866 in 88 s with `HETEROES_EXHAUSTIVE=deep` (no failure found). Hypothesis and SimPy are a test extra (`pip install -e .[test]`); without them those tests are skipped.
- **Measured for the record (`artifacts/experiments/2026-10-06-coefficient-residue/`, script and output kept):** a generation record is 744 bytes for 8 candidates (1,883 for 32; 6,747 for 128) against a 0.99 GB model. With rewards k/96, another order of the float64 sums changed the float32 coefficients in 0.30 to 0.40% of 20,000 random sets (N = 8, 16, 64), always as `0.0` against a residue of about 1e-16 (a reward equal to the mean); a synthetic 2-million-element update (NumPy only) changed no FP16 weight. That is why the coefficients travel. Not measured: two real machines computing different coefficients; the effect on the real model.
- **MASTER Gate G2 (§22.4), what the evidence says:** invariants with a deterministic fake oracle: yes (the scenarios and the model of the contract); protocol and commit ADR: written (ADR-002, pending review); "remote worker abstraction smoke": only fake workers inside the tests, there is no worker protocol or service yet (the endpoint table of ADR-002 is a proposal).
- **Not done / not verified for the ledger:** (updated in the evening: the ledger now runs on the 1660S, Python 3.14, and with real threads, see the G3 bullets above) the restart procedure of the coordinator (the record is in the ledger, the procedure is not written); the chain parent → child between generations is not enforced by `open_generation`; no migration of the schema (version 5); worker ids are free strings; `max_attempts` is a policy of the process. See `TODO.md`, group `ledger-next`.
- **Next action:** (1) the owner reviews the work of 05/10 and 06/10 (ADR-002 first; the G3 code and the README of `2026-10-06-g3-two-machines-cable`) and pushes. (2) MASTER §22.6 (Sprint 4): C1 admission and profiling, the proportional baseline (B2), C2 scheduling; before any claim of speedup profile the coordinator's update (about 46 s per generation) and the synchronization. (3) Decide with the owner: whether `open_generation` should enforce the chain parent → child; the restart procedure of the coordinator (SUPPORTING in MASTER). (4) The failure campaign on the physical machines (C3/E6) and the cleanup of the 1660S and its password (switch to the SSH key only). (5) Learning (TODO group `learning`) can run in the gaps when a GPU is free. Small items: `TODO.md`.

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
