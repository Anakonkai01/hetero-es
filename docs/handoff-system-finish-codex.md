# System finish — Codex session paused by owner (2026-10-20)

Read `../AGENTS.md` first, then this file and `handoff-system-finish.md`. The owner explicitly paused because usage was
nearly exhausted. Do not infer permission to resume from this handoff. Branch `feat/v3-audit-recovery`; nothing pushed,
tagged, published or deployed. The live r10 lab and live device approvals are untouched.

## Completed code

| Commit | Change |
| --- | --- |
| 01001e6 | Web type/hook fixes; preserve the user's cleared default-coordinator selection |
| 67a850b, 19d4053 | Optional candidate seed group shared across different run IDs/layouts; accessible input |
| c1cb6fd | `heteroes manifest` for safe local pinned snapshots; refuses executable/pickled files and overwrites |
| 637fce3 | Native Windows must not inspect WSL driver libraries; precise launch intent before/after process creation |
| b1637b7 | CPU-safe new-model reference validation and repeated full-model signed probes |
| b41a904 | Contribution OFF keeps queued runs waiting; active runs cancel safely; revocation still cancels the queue |
| 368085a | New-model qualification from web/API through an owned agent subprocess, per-device admission and cancellation |

The qualification feature is implemented but has NOT been exercised on packaged GPUs. It establishes one immutable
reference per workspace/manifest, compares every signed repeat on the CPU lab, binds dynamic admission to the raw native
self-test hash without changing the native Windows self-test document, and holds the physical GPU until confirmed death.
Restore mismatches quarantine the device. Credentials travel to the child through its environment, not argv/input files.
The web Models page now offers a device picker, start/cancel/progress and the manifest CLI example.

## Acceptance and evidence

- Baseline `9e68c65d77064e9499a92b3c95703cf4` COMPLETED 4/4. Records, coefficients, chain and final file verified.
  Final-generation weights: `670ac40ce4322638968d276f70da23e411f3e98c0187497ec1ca8a5120883ecb`.
  Selected/exported generation 1: `1c1e4e7a7273fa60e46c7d7054773d7d0c42378b63ef494358eac1f5ed94ff0f`.
  Export file checks and independent reload passed. These are system observations, not a learning claim.
- First two-device attempt `302ceac1c87743698258f649974ea767` failed BEFORE spawning the Windows worker and was cancelled.
  The old unknown intent was retained as `launch-intent.failed-before-spawn.json` only after verifying the exact old
  source SHA, cancellation fence, absent process/stdout and absent matching native process. See the Windows evidence.
- Native packaged Windows GPU self-tests passed, including after installing fix1. Native CPU reproduction of the old
  WSL-path failure now passes environment preparation and process creation. Both Linux and Windows use unmodified fix1
  Worker runtimes from `637fce3` for the second run.
- Second two-device run **`6590307f291e4fd3b0774b42bbda7562` is still running**. Same baseline configuration with
  `candidateSeedNamespace=9e68c65d77064e9499a92b3c95703cf4`. At the final pause checkpoint: all four generations match baseline weight hashes,
  all 5 cross-device audits match and all 64 candidates are committed. The latest immutable sampled state is
  `evidence/2026-10-20-system-finish/two-machine-pause-checkpoint.json`; inspect actual current state before claiming final
  acceptance. The job has four generations and then validation/export; it remains running in the isolated lab.
- Initial check-all found web type/lint issues (fixed) and a fixture failure caused by concurrent root defaults mutation
  (restored). The next complete invocation passed everything except the seed input label (fixed; targeted browser passed).
- Sampler 4/4 mutants; seed runtime 4/4, managed propagation 1/1 and backend propagation 3/3; manifest 4/4; Windows launch
  4/4; qualification reference 4/4; qualification backend 5/5 and agent 5/5; contribution queue 3/3.
- Qualification backend suite 348 passed; runtime product/transfer 23 passed and extra agent/reference regression 73 passed.
  Browser start/cancel passed against a disposable CPU lab. See `evidence/2026-10-20-model-qualification/README.md` for
  initial harness failures, corrected receipts and limits. Raw synthetic bearer logs are ignored; public copies redacted.
- A NEW full `scripts/check-all.sh` invocation is running against `368085a`:
  `.scratch/check-all-model-qualification.log`, receipts `evidence/2026-10-20-system-finish/checks-model-qualification/`.
  Runtime tests, Python lint, Prettier and source-package imports have passed; Python format has failed. Backend tests
  were still running at the final read. Inspect `python-format.log` and the eventual final result before resuming; do not
  claim a clean full check.
  This active receipt directory is ignored temporarily so unfinished files are not committed as immutable evidence.

All new system/Windows/queue evidence is in dated directories; old Claude evidence was retained unchanged. Generated root
profiles/tarballs from the earlier preflight were restored: they were stale, not a final candidate3 release.

## Running isolated apps and Windows restore — important

Lab: `http://100.110.165.40:8790`, workspace `bcbece5a24834ac28e358fc49db1343f`.
API helper `.scratch/isolated-lab/api.py` must run from its directory; `login('researcher'|'admin')` reads private files.
Never print login replies, tokens or private config contents.

- Server source `67a850b`: `.scratch/isolated-lab/start-seed.sh`; driver PID 2480107, wrapper 2480093.
- Linux Worker source `637fce3`: `.scratch/isolated-lab/worker5070/start-fix1.sh`; driver PID 2771457.
  Driver commands/results are `worker5070/{commands,results}.jsonl`; append one action, wait for its result before dependent
  actions. `login` uses `{"action":"login","login":"researcher"}`. `quit` closes the app before the renderer can reply,
  so verify exact process death instead of treating the resulting closed-page error as failure to quit.
- 5070 device `5e1b71846ce4404b9d919ec87023dd78`, worker `desktop-906949218c43`.
  Active runtime `worker5070/xdg/config/@heteroes/worker/runtimes/3712ad25fb38`.
- Isolated Windows device `106afff249ef4882b37943fddadc3fe7`, worker `desktop-6d6e5328c3d1`.
  Active native runtime `D:\HeteroES-Worker-data\runtimes\fa233c42bd80`.
- Packaged fix1 artifacts: `.scratch/r11-builds/lf1-20261020-r11-candidate3-preflight-fix1/`.
  These are preflight artifacts, not the final release and do not contain `368085a` qualification or the queue change.
- SSH was expressly authorized THIS session for `thao_nguyen@100.92.20.58`; it lands in WSL. Native PowerShell is
  `/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`; native Windows Tailscale IP `100.81.45.107`.
  A future session must obtain current SSH authorization under AGENTS.md; old permission does not transfer.

**The original Windows Worker is still backed up and must be restored after the remaining Windows acceptance.**
Original user data was moved intact to `C:\Users\Thao Nguyen\AppData\Roaming\@heteroes\worker-system-finish-backup`.
Original program, registry exports, shortcuts and credential hashes are backed up privately in
`C:\Users\Thao Nguyen\AppData\Local\Temp\heteroes-system-finish` (`original-program`, `restore-state.json`).
The running test app uses fresh isolated data at the normal Worker userData path, and D: storage created for this task.
Do NOT launch, approve or enable the original revoked live identity.

Helpers in `.scratch/windows-system-finish/`: `action.py ACTION`, `run-ps.py FILE`, `driver.cjs`, `restore.ps1`.
Native remote driver at the temp path above controls the real app through local CDP ports 19323/19324. `selftest` appends
`--gpu` and app launch sets `HETEROES_GPU_ACCEPTANCE=1`. `contribution-args.json` currently enables contribution.
Raw action replies can contain private session data; never print or commit them. `restore.ps1` exists both locally and
remotely. Before restoring: drain/quit the test Worker, uninstall its test installation, verify only the owned test app/data
were removed, then run the restore script. It restores original program/data/registry/shortcuts and verifies credential
hashes, without launching the original app. Remove the private copied researcher login from the remote test directory
when cleanup is complete. Do not delete the private backup before verification.

Stop isolated apps only after drain: contribution OFF, quit, verify exact app/process exit; then SIGTERM the exact driver
PID after checking `/proc/<pid>/cwd` and argv. Server driver handles service.stop on SIGTERM. Do not use broad kill patterns
or the old worker `stop.sh` blindly. Never touch the live unit/controller/database.

System disk has about 27 GB free (check again before builds). Isolated Linux runtimes consume ~15 GB and previous builds
~6 GB. Keep private runtimes/state on system storage; Archive UUID `10443D1F443D094C` has ~259 GB free for artifacts.
No cache cleanup was performed at pause.

## Resume order

1. Inspect final CPU check and current two-machine run. If complete, record all four records, seeds/rewards/coefficients,
   child hashes, audits, final export and independent reload versus baseline. Record timings with the limit that CPU
   tests/builds ran concurrently; do not claim a controlled speed benchmark. Preserve failed first attempt separately.
2. Package qualification source `368085a` in clean detached worktree `.scratch/model-probe-source` (npm ci already done;
   **build has not started**). Build to a fresh directory, preferably Archive for artifacts; do not mutate root defaults
   during check-all. Upgrade isolated apps only after the run drains, then prove new-model qualification on a genuinely
   different safe pinned model on both GPUs. CPU/web fixtures are not that proof. Use the CLI manifest helper.
3. Remaining original steps 5–8 are still open: Python rewards on web/coordinator subprocess, 1 GB/10m-row file-backed
   datasets/admin limits, any machine coordinator including native Windows with a pinned adapter; hf_compact v3, isolated
   vLLM probe, eval/compare/serve/worker CLI, prompt format/boxed scorer/accounting, UI friction 12, final candidate3 and
   flag-day checklist. Do not deploy/push; final flag-day decision belongs to the owner.
4. An observed metadata issue to investigate: packaged `runtime_info.code_info()` walks to an enclosing Git checkout,
   so this isolated run reports the current root branch commit/dirty state rather than packaged source commit `637fce3`.
   The receipts explicitly identify package source and self-test source tree hashes. Add a meaningful regression before
   changing provenance; do not rewrite existing recorded observations.

## Session 2 (Sonnet 5.5, 2026-10-20 afternoon) — resumed by the owner

The owner resumed work and asked that this session stop before complex logic/code; a stronger model takes those items.

Done:

- `755ca33` formats the Windows launch call in `remote.py` (Python AST unchanged; the only failure of the earlier check).
- Run `6590307f291e4fd3b0774b42bbda7562` had been left in DRAINING when the isolated apps were stopped. Restarting the isolated
  server (`start-seed.sh`) and the Linux Worker (`worker5070/start-fix1.sh`, then `login` and `contribution enabled`
  through the driver) let it finish: COMPLETED. `580f23d` records it in `docs/evidence/2026-10-20-system-finish/two-machine-final.json`
  (script `.scratch/record-two-machine.py`): every generation record, child hash, final weights, selection and export equals
  the one-machine baseline; 5/5 audits matched; no quarantine. Limits are written in that README (pause, concurrent CPU work).
- A new full `scripts/check-all.sh` was started against `580f23d`: `.scratch/check-all-final.log`, receipts
  `docs/evidence/2026-10-20-system-finish/checks-model-qualification-final/` (result: ALL PASS).
- The owner authorized SSH to both borrowed 3060s for this work: `thao_nguyen@100.92.20.58` and `quang@100.99.227.8`
  (both land in WSL Ubuntu, RTX 3060, driver 617.42). Windows installer tests come later. Reachability was verified only
  (read-only commands). Findings: no `node`/`xvfb` in either WSL, so the Electron Worker is not the route there;
  `~/heteroes-venv/bin/python -c "import torch"` segfaults unless `LD_LIBRARY_PATH=/usr/lib/wsl/lib` is set; Thao's WSL has
  `~/heteroes-system-finish` and `~/heteroes-v3-acceptance-20261019`, Quang's has only an old `~/projects/heteroes`.

Left for a stronger model (not started on purpose):

1. `runtime_info.code_info()` provenance: `REPO_ROOT` is `parents[2]` of the module and the git calls walk to any enclosing
   checkout, so a packaged runtime under `.scratch/` reports the checkout. Idea only: report git info only when
   `runtime_info.py` itself is tracked (`git ls-files --error-unmatch`). Needs a regression test first and a check of
   `runner.py` lines 142/250/283 and `qualification*.py` consumers.
2. Package `368085a` (clean worktree `.scratch/model-probe-source`, build not started) and prove new-model qualification
   on real GPUs with a different safe pinned model. For the 3060s the headless route is
   `python -m heteroes.product.agent enroll|run --config <json>` (needs a pairing code, `serverUrl`, `computeUrl`,
   `modelPath`, `workerId`, `stateDirectory`) with the worker runtime copied to WSL; this has NOT been tried.
3. Original steps 5-8 (Python rewards, 1 GB/10m-row datasets, any-machine coordinator, `hf_compact` v3, vLLM probe, CLI, prompt
   format/boxed scorer, UI friction 12, final candidate3, flag-day checklist). The flag-day decision is the owner's.
4. Windows: the isolated test Worker and the backup of the original are still in place on Thao's native Windows
   (see the restore section above). Restore after the installer tests.
