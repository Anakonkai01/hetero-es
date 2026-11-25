# HeteroES final acceptance checklist

The release requires all 37 registered check–environment pairs on one clean source tree. The live lab, notebook, D1 regression tests and Countdown experiment also need receipts that identify the code and hardware used. Record `PASS`, `FAIL`, `NOT_RUN`, `DEFERRED` or `OPEN` and an evidence path for each result. Use the generated [acceptance report](README.md) for the matrix and the [workstation operations guide](../guides/local-lab-operations.md) for the live lab.

Checked matrix items refer to [candidate source `src-95182970…`](STATUS-src-95182970.md) (commit `40c644af`, 26/11): 23 of the 26 local pairs pass (CPU, packaging, all 12 mutation groups, GPU, performance). The three `faults` pairs (`strict-e2e`, `-soak`, `-int8`) need Thảo's RTX 3060 as the second machine and could not start (SSH timeout, machine off). The 11 RTX 3060 pairs are not rerun yet.

## 1. Prepare the candidate and hosts

- [ ] Record the candidate commit, source ID, verified model and dataset identities, Python/CUDA versions, GPU/driver, OS and boot mode.
- [ ] Check GPU availability and lab reservations before starting. Run Thảo’s RTX 3060 WSL and native Windows jobs serially. Keep controlled throughput measurements free of loaner activity and concurrent GPU workloads.
- [ ] Use Quang’s RTX 3060 as a best-effort additional worker. Record its software, GPU usage and free VRAM at start, time windows of contention or absence, completed candidates, retries and audit outcomes. Let normal lease handling cover lost workers. Keep the owner’s game and other applications independent of the worker.
- [ ] On the borrowed RTX 3060 Laptop GPU (6 GiB), verify the WSL and Tailscale route and CUDA. Record power mode, available VRAM and driver. Qualify the pinned model for the configured chunk and run a short worker smoke test before adding the laptop to a run. Record participation independently of Quang’s.
- [ ] Record supplemental laptop acceptance against the final source, including noise and update checks, strict Qwen parity and a distributed worker smoke test. State GPU, driver, CUDA/PyTorch versions, VRAM available, applicable test counts, and any resource contention.
- [ ] Freeze the candidate after code, tests and notebook changes. Stage the same commit for remote runs. Regenerate affected receipts whenever the source ID changes.

## 2. D1 and continuation regressions

- [ ] Cover strict creation, dispatch, joining, retrying, leaving and rejoining with a GPU coordinator. Cover both one device in two roles and separate device aliases of one physical GPU.
- [ ] For a coordinator and one worker on the same GPU, allow the same-model estimate below and exactly at 90% of total VRAM. Refuse an estimate above the threshold, a missing or unusable qualification, or measurements that do not cover the selected run configuration. Check selection of the applicable model, device and measurement.
- [ ] Preserve acceptance for distinct GPUs and the existing layout rules for earlier recipes. Keep strict coordinators on GPU. Reject two workers using one physical GPU and reject an unrelated run that tries to reserve a held GPU.
- [ ] Verify that leaving releases the worker role while the coordinator retains its device and physical GPU reservations. Verify retry, rejoin, pause, recovery and final release. Check that scheduling and creation return actionable reasons when they refuse the layout.
- [x] Run the backend suite and the updated `gpu-ownership-backend` mutation group. Reconcile ADR-013, the acceptance registry wording and the form’s coordinator suggestion with the behavior demonstrated by the tests.
- [ ] Check continuation from the CLI/SDK, including source SHA, the new generation-0 parent SHA, and validation of model, checkpoint and artifact integrity. Verify the expected rejection when a source has no usable checkpoint or its bytes fail verification.
- [ ] Exercise **Continue** on the web run page. Test same-workspace `READY` selection, non-`READY` and cross-workspace rejection, model compatibility, receipt lineage and the exact initial parent SHA in the new run.

## 3. Registered 37-pair matrix

Run the profiles through `scripts/accept.py` with `--keep`, using the GPU opt-in for GPU-bearing profiles. The CPU, 5070 Ti, 3060 WSL and 3060 native roles below use the environments configured in the registry. Quang’s 3060 and the RTX 3060 Laptop GPU provide additional worker evidence.

### Local CPU and build profiles (3)

- [x] `acceptance-selftest`
- [x] `check-all` — runtime/backend tests, lint, format, source imports, frontend/desktop tests, builds, i18n and browser/Electron contracts.
- [x] `package-linux` — build the Worker and Server and verify packaged runtime bytes.

### RTX 5070 Ti GPU, performance and system profiles (11)

- [x] `noise-es-gpu`
- [x] `strict-gpu-suite`
- [x] `strict-parity-qwen`
- [x] `strict-parity-smol`
- [x] `strict-parity-tiny`
- [x] `strict-throughput` — golden tokens and throughput floor.
- [x] `int8-memory` — resource measurements for the frozen-int8 LoRA path.
- [x] `strict-phase-trace` — stage timings and peak memory.
- [ ] `strict-e2e` — healthy two-GPU run, worker loss during an active lease, equal generation records and child hashes, CPU replay.
- [ ] `strict-e2e-soak` — 600 generations, correct replay and the registered bookkeeping growth limit.
- [ ] `strict-e2e-int8` — two-GPU frozen-int8 LoRA lifecycle.

### Local mutation profile (12)

- [x] `mutation-strict-routes`
- [x] `mutation-watchdog`
- [x] `mutation-restore-recovery`
- [x] `mutation-strict-mismatch`
- [x] `mutation-audit-outcomes`
- [x] `mutation-recovery-io`
- [x] `mutation-strict-decoder`
- [x] `mutation-strict-qualification-runtime`
- [x] `mutation-strict-qualification-backend`
- [x] `mutation-gpu-ownership-backend`
- [x] `mutation-int8-lora`
- [x] `mutation-gpu-ownership-runtime`

### Thảo’s RTX 3060 WSL GPU and performance profiles (8)

- [ ] `noise-es-gpu`
- [ ] `strict-gpu-suite`
- [ ] `strict-parity-qwen`
- [ ] `strict-parity-smol`
- [ ] `strict-parity-tiny`
- [ ] `strict-throughput`
- [ ] `int8-memory`
- [ ] `strict-phase-trace`

### Thảo’s RTX 3060 native Windows GPU profile (3)

- [ ] `noise-es-gpu-native`
- [ ] `strict-gpu-suite-native`
- [ ] `strict-parity-qwen-native`

### Matrix review and release gate

- [ ] Check all receipts against the candidate source ID, host label, applicable test counts and skip bounds. Generate the candidate report and require all 37 registered pairs to pass before advancing `main`.
- [ ] Record the disposition of the separate milestone gates `M1.architectures`, `M3.bookkeeping` and `M5.release`. Record `M3.full-disk` as `DEFERRED` for this release by the owner’s decision on 2026-11-24. Link the release receipt when the candidate is deployed and rollback is verified.

## 4. Countdown follow-up and GPU notebook

- [ ] Preserve `countdown-dist2` and its 90-generation ledger. Verify the final published weight file against the applied generation-89 SHA before deriving a new model.
- [ ] Continue Countdown in fresh, linked run directories. Verify each generation-0 parent against the preceding final child SHA. Record the 500-generation target, four-hour wall-clock limit, hyperparameters, candidate seeds, worker roster and dataset split hashes before launch. Record the actual applied count and elapsed time at the end.
- [ ] Monitor progress, worker activity, audits and available disk throughout the standalone run. Check validation at segment boundaries. If improvement stalls, stop at a published checkpoint and start another segment with the selected alpha or sigma change, recording the reason and the new recipe. Allow time inside the limit to verify the last applied checkpoint.
- [ ] Freeze the checkpoint selection and report plan before opening test scores. Record the original base, generation 89 and the selected continuation checkpoint, with each model’s SHA.
- [ ] Score exact equations separately from format reward. Record the original 250-row split and the 249 rows with no train puzzle overlap. Preserve ordered rows, counts, paired comparisons, checkpoint hashes and scorer identity with the results.
- [ ] Report the four matching one-GPU and distributed generations over the same window. Record full-run distributed timings and the actual worker roster for each run, including contention on borrowed machines.
- [ ] Run `runtime/notebooks/demo.ipynb` from top to bottom in a fresh `ai` kernel on GPU. Verify model and dataset setup, the first run, scoring, model export, continuation and the second evaluation. Capture the run IDs and checkpoint identities. Exercise the Lab submit/watch path as part of the short managed smoke test.

## 5. Clean lab installation and managed smoke test

- [ ] Check the Archive storage volume UUID and available space. Record the previous deployed commit, back up the existing state/config and establish a fresh database and object store. Verify startup and rollback procedures through the lab’s supported operator commands.
- [ ] Deploy the accepted commit, build the web app and prepare the worker installers. Verify local `status`, `doctor`, login, fresh object write/read and workspace creation. Confirm the agreed administrator credential setup before reopening the existing domains.
- [ ] Verify the public web and compute endpoints. Re-pair and approve the two primary workers with the owner. Verify the model and dataset uploads, checksums, qualification, physical GPU identities and contribution state. Pair loaner workers only as available.
- [ ] Submit a short strict managed run with the 5070 Ti coordinator and co-located worker plus a remote worker. Verify assignment, candidate distribution, generation progress, zero audit mismatches, final verified checkpoint and release of reservations.
- [ ] Exercise pause/resume, withdrawal/rejoin of a remote worker and leave/rejoin of the co-located worker. Verify the requested transitions in the web UI and ledger, correct recovery lineage and uninterrupted ownership of the coordinator’s GPU during worker leave.
- [ ] Verify the terminal checkpoint still appears after a periodic or delayed upload. Download and verify recovery artifacts. Exercise the continuation path included in the release.

## 6. Evidence and submission

- [ ] Save dated, reproducible receipts for the final candidate, the managed smoke test and both learning tasks. Record any hardware contention, missing evidence and limits of the claims. Regenerate the evidence index and update the current handoff with the actual deployment state.
- [ ] Update the TDTU Word report and PDF, slide deck, live demo script and backup video. Verify 50–70 pages, layout, table of contents, Vietnamese text, division of work and that every numerical claim traces to its run or receipt. Use the 20–30 minute presentation target and the owner’s chapter review.
