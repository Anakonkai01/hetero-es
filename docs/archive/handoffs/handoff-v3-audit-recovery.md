# Handoff to Claude — v3 audit/recovery/GPU/SDK, r11 still WIP

Session closed at the owner's request to conserve the remaining usage. Written
2026-10-19. Start here, then read `../AGENTS.md`, `HANDOFF.md`,
`handoff-v3-extensibility.md`, `handoff-v3-product-integration.md` and ADR-008.
Do not treat an incomplete r11 module or a passing native run as release acceptance.

## 1. Checkout and exact stopping point

- Repository: `/home/pc5070ti/projects/heteroes`.
- Branch: **feat/v3-audit-recovery**, forked from **30bc689** on
  feat/v3-product-integration. Claude's original branch is feat/extensibility-step0
  ending a804eac. Prior product integration completed original handoff steps 1–3.
- Before this handoff commit, HEAD is **991b70e**. Everything is committed; the
  handoff itself will be one additional docs commit. Nothing pushed, tagged,
  merged into main, published or deployed.
- Latest COMPLETE full acceptance: **e35811c**, 22/22 ALL PASS,
  **2,273 runtime passed / 100 skipped**, **302 backend passed**.
- Later **69534ec** adds native-probe path/storage helpers (5 targeted tests pass).
  Later **627b89e** is explicitly WIP r11 reference verification (1 pure verifier
  test passes). Neither later change has a complete check-all or mutation receipt.
- No background GPU, pip resolver or check-all process remains. All subprocess
  sessions finished before evidence was committed. Worktree was clean before
  writing this document.

### Commits in this continuation

| Commit | Result |
| --- | --- |
| aebe64e | Deterministic text audit wrapper, coordinator/worker integration, authenticated backend quarantine and UI |
| c033fe8 | Complete v3 recovery state and shared safe manifest metadata |
| 912b35e | GPU qualification script/tests and preregistration before runs |
| 0bbf881 | Pre-generation scorer-config correction with failing regression first |
| d05503d | Download CLI accepts/validates format-2 recovery objects |
| 50efe9d | Completed audit CPU evidence |
| e35811c | Installed CLI aliases, runnable SDK examples and reward guidance |
| e12a8fb | Completed paired Linux/WSL GPU evidence |
| 0e2ac36 | Completed recovery and final SDK/combined CPU evidence |
| 69534ec | Native Windows protocol, portable source paths and separate bulk directories |
| 627b89e | **WIP**, unwired product/qualification_v3.py and pure verifier test |
| 991b70e | Native Windows results including LoRA boundary failure; resolver inputs and WIP limits |

## 2. Owner authorization and decisions that persist

The owner explicitly allowed GPU work, SSH to thaonguyen's 3060, then selected
**Windows on that same 3060** for installer acceptance. Do not ask again for those
same permissions. Inform the owner when a concrete installer is ready for
installation/run/uninstallation checks. No installer has been built in this
continuation, and no installer acceptance has happened.

SSH works by key: `ssh -o BatchMode=yes thao_nguyen@100.92.20.58`.
Host/alias supplied by owner: desktop-qp0nta7. It is WSL2, with native Windows
available through `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`.
No sudo was needed. Do not put any conversational credentials into files/logs.

Authorization does NOT change lab/device state: **3060-thao remains REVOKED** in
the last live read. No approval/contribution changes, pairing, live job, deployment,
server restart, push, merge or tag occurred. Use isolated fixtures for product tests.
The live deployment remains separate from this branch. The owner still decides
the flag day. Keep legacy RUN paths until that decision; retain old replay/goldens.

Broader research hooks (arbitrary update/optimizer plugins, custom sigma callbacks,
etc.) were explicitly deferred. Do not expand this work into those features.
All 12 accepted decisions/Q-A…Q-D remain in the original handoff/ADR; do not reopen.

Protected files: **noise/**, **es/**, **ledger/**, **generation_record.py** and
**worker_api.py**. None changed after 30bc689. Evidence:
`evidence/2026-10-19-v3-sdk/protected-files.json`. Ask separately if a behavior change
there becomes necessary. Do not alter Conda ai, /mnt/sekai, generated resource
profiles by hand, historical artifacts or committed evidence.

## 3. What is now complete

### Audit scheduling (original step 4)

`runtime/src/heteroes/v3/audit.py` wraps the unchanged WorkerAPI. It samples candidate
IDs deterministically (default exactly 1/20 of the SHA-256 space), leases committed
texts to a DIFFERENT admitted worker and submits hashes through the existing
Ledger.record_audit transaction. The wrapper reads live canonical rows under the
ledger connection lock; it does not write SQL into the protected ledger module.

Operational audit leases are in memory, token/auth/descriptor bound, heartbeatable,
expiring and retryable. Completed canonical audits survive restart and are not
reissued. Generation draining keeps the same parent/context until audits finish.
Cancellation stops new audits. No second worker or a bounded timeout emits
`audit_incomplete`; it does not manufacture a pass or rewrite rewards.

Three mismatches quarantine BOTH workers through the existing ledger rule. Original
and auditor receive quarantine state even at final shutdown. Exact restore failure
is fatal and retained separately in private `audit-faults.json`, without pretending
it was a completed audit on an already-committed attempt. Managed runner explicitly
places this file under the private run root, even with separate bulk storage.

Files: coordinator.py, worker.py (optional audit_id envelope and AUDITED result),
worker_runtime.py, product/runner.py, v3/local.py; product/run_supervisor.py projects
auditSummary. Backend agent_polling accepts current authenticated coordinator events
only for selected workers, only when newly inserted, without overwriting REVOKED.
Store/timeline and RuntimeResults/eventText/translations show counts and warnings.

Tests include spoofed credentials/tokens/hashes, expiry/reassignment, cancellation,
restart, failure vs mismatch, three mismatches, reward immutability and two actual
CPU HTTP workers with all 8 candidates audited plus independent record replay.
8 runtime + 2 backend mutants killed; full audit check: 22/22, 2262 runtime/301 backend.

### Complete v3 recovery (additional pre-flag-day requirement)

New shared stdlib module `heteroes/recovery_manifest.py` is shipped in the Lab Server
subset through backend/runtime_sources.py. Format 1 remains for legacy points;
format 2 has strict allowlisted names and bounded metadata/state.

`product/recovery.py` plus `v3/recovery.py` capture ledger, parent/child weights,
frozen recipe/plan/dataset, pinned initial adapter, earlier best weights, validation
history and audit restore faults. Missing selection is an error, never a reset.
Recipe/plan/dataset/selection/history and pinned adapter identities are checked.

Restore rebinds dataset/model-manifest paths, reconstructs metrics with test locked,
retains best selection and holds dispatch. Operator provisions the exact pinned
base-model files at the replacement installation's private path. No grants,
credentials, process IDs or stale export receipt are restored. The download CLI in
scripts/recovery.py now validates metadata and accepts the new paths too.

Tests: real managed full/LoRA runs, save generation-0 point, DELETE source run dir,
restore elsewhere with separately provisioned base path, resume and compare both
final hashes/selection/verified export. Distinct synthetic earlier-best bytes test
retention independently of current parent/child. Tiny managed runs may be no-op;
nonzero updates are covered separately, so do not claim learning from those tests.
Mock download-service test executes the actual CLI. 5 mutants killed. Recovery
check at 912b35e: 22/22, 2269 runtime/302 backend; final e35811c also covers downloader fix.

### SDK polish (original step 8)

runtime/pyproject.toml registers `heteroes = heteroes.v3.__main__:main`.
`python -m heteroes`, `python -m heteroes.v3` and installed `heteroes run` share one
runner. Added runtime/examples/v3/{train.py,keyword_reward.py}; updated local and
managed guides. Python rewards are trusted coordinator code, no sandbox, saved
top-level function, finite per-row outputs. Source-file hash does not automatically
pin imported helpers/services; docs explain the reproducibility responsibility.

Wheel built/installed into a NEW scratch venv inheriting verified numerical deps;
actual installed console command completes a CPU generation. Existing envs were
not modified. 2 entry-point mutants killed. Complete e35811c check: 22/22,
2273 runtime/100 skipped, 302 backend. Arbitrary update rules remain deferred.

### Qwen GPU acceptance (engineering portion of original step 7)

Protocols in docs/v3-gpu-qualification-2026-10-19.md and
runtime/scripts/v3_gpu_acceptance.py. Pinned Qwen 0.5B, canonical CPU noise,
FP32 evaluation, two HTTP workers, antithetic population 4, 2 generations,
4 prompts/candidate, forced 100% audits, independent re-scoring and CPU replay.

All six Linux/WSL cells (full/subset/LoRA on 5070 Ti and 3060) pass. **96 cross-GPU
texts identical**, **48 matching audits**, all rewards/recipes/plans/records/child
hashes match. Full has 2 non-noop updates per GPU; subset/LoRA have none. This is
not learning acceptance, not one cross-machine distributed job and not 1660S evidence.
First scorer-config launch errors are preserved; no candidates/rewards preceded
that correction. 5 probe gate/comparison mutants killed.

## 4. Native Windows results — CRITICAL boundary for the next agent

Owner selected the 3060's Windows. All three native cells independently complete
8 candidates, 8 matching audits and exact independent CPU replay. **Full and subset
also PASS exact comparison against the 5070 Ti** (32 texts each, all identities,
rewards/records/children). Full updates are nonzero.

**LoRA cross-OS comparison FAILS at recipeHash.** Only recipe difference:
`/weightSpace/initialAdapterSha256`.

- Linux/WSL seed-7 initialization:
  `051b79e34551eddac13dc3029743c32418bb332b3947b5b6b1249c9145e86b1e`.
- Native Windows seed-7 initialization:
  `7964e412641cbc76c32407c63539183fc5c4785370e8c396aaec26a381c35261`.

See immutable `evidence/2026-10-19-v3-windows/lora-recipe-diff.json` and
compare-lora.log. Deeper cause is **not established**; do not guess it is a noise,
restore or ledger fault. Those native runs replay exactly for their own identity.
Do not weaken comparison or silently overwrite the failure.

The supported product design already pins/transfers coordinator initial adapters.
NEXT useful acceptance: native Windows WORKER consumes the exact Linux adapter,
rather than acting as a local coordinator that independently initializes one.
Windows coordinator is unsupported. This next test has NOT happened. Suggested
source file: `.scratch/v3-gpu-20261019/5070ti-lora-second/run/initial-adapter.bin`.
Verify the first SHA above after transfer; use existing product/v3.prepare_run
worker path or v3.model.trainable_schema with declared weightSpace/adapter.
Prefer eventually exercising the actual worker CLI/private transfer and audits
against an isolated Linux coordinator. No protected numerical changes are implied.

## 5. r11 WIP — what exists and what is still missing

**627b89e** stages `runtime/src/heteroes/product/qualification_v3.py` and
`runtime/tests/v3/test_v3_qualification.py`. Pure verify() checks two repeated
positive and negative observations against reference hashes/texts/rewards/restore.
One test passes. observe()/qualify() are only an unexercised draft.

It is NOT wired to product/qualification.main, no bundled v3 reference exists,
no backend native Windows admission has been enabled and no generated profile or
installer changed. The draft initializes an adapter and compares it to the
reference; the native result above means this assumption must be redesigned for
Windows around a pinned canonical adapter. Treat this module as WIP, not a feature.

Native resolver inputs ARE ready:
`evidence/2026-10-19-v3-windows/{linux,windows}-pip-report.json` and pins/logs.
Linux report: **56 wheels**; native Windows: **38 wheels**. Existing pins plus
PEFT 0.21.2, Accelerate 1.15.0, psutil 7.2.2. These were resolved on their actual
OS/interpreter, NOT pip --platform marker emulation. Also in .scratch/v3-r11-reports.

Next steps, in order:

1. Qualify native LoRA worker with canonical Linux adapter; preserve first failed
   result. Add failing tests before any production/probe changes and mutate helpers.
2. Complete reference generation and qualification_v3 integration tests (tiny CPU
   first, then real hardware). Reference must bind model/schema/recipe/plan, both
   signs, raw text hashes/rewards, exact restore and canonical adapter. Do not let a
   synthetic fixture declaration become real device compatibility evidence.
3. Finish safe profile generation. scripts/build-worker-profile.py currently writes
   desktop/worker/resources directly, names desktop-v1, copies legacy reference.
   Add a fresh scratch output option and explicit v3 reference/profile selection;
   use the actual pip reports. NEVER hand-edit requirements/profile JSON. Preserve
   existing dependencies/OS marker semantics; pin all new wheel hashes/sizes.
4. Wire qualification.main to choose v3 only for a v3 reference/profile. Setup's
   READY metadata currently hardcodes desktop-v1; service.cjs sends qualification
   updates only for recipeVersions.includes(2). Update with tests/mutations.
5. Backend device_models.SelfTest currently restricts native Windows to v1 and
   policies.v3_qualification rejects Windows. Enable v3 worker-only admission ONLY
   with real reference-bound evidence, after the above acceptance. Keep the legacy
   route until the owner picks the flag day; v3 devices advertise exactly [3].
6. Build actual fresh r11 Worker/Lab Server candidates into scratch/new output,
   no publication. Tell owner when installer is concrete and ready. Check Windows
   C free space first: it had only ~3.4 GiB; reuse of an existing interpreter here
   does not establish a fresh installer can fit. Do not clean user data yourself.
7. Real installer install/run v3/restart/stop/uninstall acceptance with owner;
   only then coordinate the owner's server+r11 flag day. No deployment approval
   has been given and the existing live device is revoked.
8. First learning experiments remain future work: separate preregistration before
   running, independent seeds/budgets, validation/test and separate space reporting.

Run full check-all and mutations for each completed step, new evidence folders.
Last full suite does NOT qualify the later native helpers or the WIP r11 module.

## 6. Machines, paths and safe commands

Local verified numerical environment:
`$HOME/miniforge3/envs/heteroes-match/bin/python` (Torch 2.13.0+cu132,
Transformers 5.17.0, NumPy 2.5.3, PEFT 0.21.2). Do not change Conda ai.
CPU: CUDA_VISIBLE_DEVICES=''. GPU: explicit --gpu when supported AND
HETEROES_GPU_ACCEPTANCE=1. New GPU roots stay private, never /mnt/sekai.

Local scratch:

- `.scratch/v3-gpu-20261019/5070ti-{full,subset,lora}-second/` (private ledgers,
  weights, adapters; do not commit raw attempt credentials).
- `.scratch/v3-sdk-venv`, `.scratch/v3-sdk-project`, `.scratch/v3-sdk-installed`.
- `.scratch/v3-r11-reports/{linux,windows}.{in,json}`.
- `.scratch/v3-native-{inspect,prepare,run}.ps1`, v3-native-driver.py and
  v3-export-qualification.py. Committed Windows evidence includes copies of the
  useful harness scripts with .txt suffix for later recovery.

WSL 3060:

- SSH account **thao_nguyen**, IP **100.92.20.58** (not thaonguyen).
- `~/heteroes-venv/bin/python`: CPython 3.14.4, same Torch/Transformers/NumPy.
- `~/projects/heteroes-v3-acceptance-20261019`: frozen 0bbf881 source, isolated
  deps (PEFT only), scripts, completed results/3060-*-second.
- Cached Qwen snapshot under ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775.
- /usr/lib/wsl/lib/nvidia-smi works; not originally in PATH.
- CUDA initially segfaulted because Linux NVIDIA 580 PTX shadowed mounted Windows
  driver libraries. Scoped qualification LD_LIBRARY_PATH was
  `/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib`.
  No system driver changes. Existing product.remote.worker_environment already
  selects matching WSL driver bytes dynamically; prefer it over hardcoding for
  future product processes. No need to re-trigger the crash.

Native Windows 3060:

- Windows 10.0.26200, PowerShell 5.1. Existing pinned interpreter:
  `C:/Users/Thao Nguyen/AppData/Roaming/@heteroes/worker/runtimes/c64f3012b965/python/python.exe`.
- Existing model: same runtime root /models/<pinned revision> (read only).
- NEW private state: `C:/Users/Thao Nguyen/AppData/Local/HeteroES-v3-20261019`.
  Source under runtime/src, probe under runtime/scripts, isolated deps, native-driver.py,
  results/windows-*-second and logs. Original installation/env unchanged.
- NEW bulk: `D:/HeteroES-v3-20261019`. NTFS/HDD_2TB,
  Volume{ac23c91d-438a-4344-8929-39fdc433c858}. About 908 GB free initially.
  Validate the same volume before writing. Published/cache directories use
  junctions; private ledgers/runtime remain on C. No other disk was used.
- Use encoded PowerShell commands (UTF-16LE/base64) to avoid shell escaping of
  paths with spaces. Do NOT use ErrorActionPreference=Stop with native stderr
  redirected through PowerShell: tqdm/retry warnings become NativeCommandError.
  The first launch failed before any candidate. Correct harness uses native Python
  subprocess.run(stdout=log, stderr=STDOUT), UTF-8 logs and actual return codes.
- Native report initially had network retries; corrected capture completed exit 0.
- Existing results/bulk/log names are occupied. New attempts need NEW names; the
  saved driver uses *-second and opens logs with x, so do not simply rerun it.

Detached worktrees (left for reuse, not running):
`/home/pc5070ti/projects/heteroes-v3-audit-check` at aebe64e;
`/home/pc5070ti/projects/heteroes-v3-recovery-check` at e35811c.
They have a .venv-backend symlink and hard-linked node_modules; untracked symlink
is expected. Check status before reusing. Serialize check-all browser ports 18090–18094.

Verification commands (fresh output folders only):

```bash
scripts/check-all.sh docs/evidence/YYYY-MM-DD-new/checks
(cd runtime && CUDA_VISIBLE_DEVICES='' PYTHONPATH=src "$HOME/miniforge3/envs/heteroes-match/bin/python" -m pytest -q)
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m pytest backend/tests -q
```

Run runtime tests from runtime/: managed tests spawn scripts/run_worker.py relative
to that directory. One interrupted audit check accidentally ran from main checkout;
its partial receipt is retained and the authoritative detached rerun passed. Never
commit an evidence folder while a background command can still append to it.

## 7. Evidence map and immutable receipts

Each folder has its own limits and SHA256SUMS. Do not edit any committed receipt;
fixes/re-runs get a NEW folder.

- 2026-10-19-v3-audit: final 22/22, 2262 runtime/301 backend, 10 mutants killed.
- 2026-10-19-v3-recovery: 22/22 at 912b35e; 5 mutants; downloader regression first/final.
- 2026-10-19-v3-gpu: six Linux/WSL cells, 96 exact cross-GPU texts, 48 audits,
  CPU replay; 5 probe mutants; first config failures preserved.
- 2026-10-19-v3-sdk: authoritative combined 22/22 at e35811c, 2273/100 skipped,
  302 backend; installed-wheel console receipt; 2 mutants; protected-file proof.
- 2026-10-19-v3-windows: native results and full/subset comparison passes,
  LoRA identity failure, actual-OS pip reports, harness/storage receipts.
- 2026-10-19-r11-profile: WIP verifier test only; no completed r11 claim.

Numerical identities from Claude's work (8 recorded recipes/418 records), prior
product steps 1–3 and their evidence remain in the linked handoffs. No older
artifact, evidence directory, published profile, installer or live source was rewritten.
