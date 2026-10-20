# Candidate6 installed; native Windows CPU guard passes; Quang offline

Current checkpoint: 2026-10-21, Asia/Ho_Chi_Minh. Continue `docs/plan-r11-release.md` in order.
This is an external connectivity wait, not a new numerical mismatch stop. The owner explicitly approved
`Triển khai decoder FP32 + CPU dự phòng, kiểm chứng tiếp`; do not reopen that answered question.
No subagents. SSH/GPU on the three named machines and pushes/FF merges remain authorized by the plan.
Every irreversible flag-day action still needs an explicit chat `đồng ý` at that step.

## What is complete

- Separate v3 `hf_fp32_cpu_guard_v1` source: `f5d311b`. GPU FP32, empirical .01 margin, selective CPU64
  reference only. Historical decoders and frozen noise/update/ledger behavior preserved. Final combined
  check 23/23 ALL PASS: runtime 2504 passed/102 skipped; backend 375 passed; 12/12 mutations killed.
- Candidate6 `lf1-20261020-r11-candidate6` prepared only. Resources `0281e04`, package receipts `e89353b`:
  `docs/evidence/2026-10-20-r11-candidate6/RESULTS.md`. Source-copy and packaged Linux Worker/Server pass.
  All installers remain private under `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate6`.
  Check Archive UUID `10443D1F443D094C` before any write there. No public manifest/link changed.
- Isolated packaged Lab Server and 5070 desktop run candidate6 with existing state/identity. Windows app
  and D: runtime upgraded. Both CLI candidate6 installs complete. Device checkpoint/predeclarations
  committed in `5c4f5de`, receipts `docs/evidence/2026-10-20-candidate6-device-upgrades/RESULTS.md`.
- Installed self-tests: 5070 GPU PASS; Thao Windows GPU PASS twice after one initial failed action;
  Thao WSL CPU coordinator PASS. Quang candidate6 self-test pending because machine went offline.
- Additional native Windows guarded-decoder probe: all nine token/text/input/weight arrays agree with
  the 5070 final-source probe; parent restore exact after each. 14 selective reference calls, GPU peak
  2.854 GiB. `docs/evidence/2026-10-21-native-windows-cpu-guard/RESULTS.md`. This extends the existing
  exact 5070/Quang nine-case proof; no 50-generation acceptance claim.
- Windows quit -> actual process exit -> reopen succeeds, preserves identity/runtime/OFF state.
  Uninstall remains AFTER the long run and BEFORE flag day; original Worker backup untouched.

Worker runtime bundle SHA256: `aa74bad820b9677fdaa1f0b81261264479c468c52b90636ae956232049596c38`.
Server runtime SHA256: `1a74f639096d7319b27d511e535ecf8661e1c5e3098538ea9602adfeaed34eca`.
Installed helper SHA256: `150ac9fdd1464e6cdb41bbc624173de28f01f53019a04f18b77e178ceb2ea95d`.
CLI runtime directory `aa74bad820b9`; desktop directories hash selected profiles instead:
Linux `1e29310e07ba`, Windows `41bf2c06ec02`. Do not guess desktop directories from bundle SHA.

## External blocker and current state

Quang `quang@100.99.227.8` SSH times out. Tailscale reports Offline, last seen October 20 18:20 UTC.
The owner was asked asynchronously to restore the machine/WSL/Tailscale. Install previously exited 0;
C: was 21,084,712,960 bytes free (21.08 decimal GB), but MUST read again before GPU acceptance.
Thao `thao_nguyen@100.92.20.58` works, lands WSL; native Windows PowerShell executable:
`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`. Thao C: about 10.51 decimal GB free;
models/runtime/artifacts on D:, no original Worker backup removal.

All four isolated devices APPROVED and contribution OFF on fresh API read; both CLI agents stopped.
Desktop agents idle. Historical attempt2 `e07deeb168ae4baaba3ac770b89043a6` remains PAUSED 13/50 with
4 audits/1 mismatch, preserved. No new managed run offered. Local main remains `086c282`, public r10
clone remains `79876cb`. This continuation commits evidence only; no merge, push, live restart or publish.

| Role | Worker ID | Device ID |
| --- | --- | --- |
| 5070 GPU | desktop-906949218c43 | 5e1b71846ce4404b9d919ec87023dd78 |
| Thao Windows GPU | desktop-9f9da13f0f82 | 8f3d691978e24167a257f018643f9165 |
| Quang WSL GPU | cli-894b5d440398 | c2db3633fe9d4edbb790881469d6dacb |
| Thao WSL CPU coordinator | cli-2ffce4b7de39 | 47e0546da4464ca484a20768ce19aca6 |

Do not use removed `desktop-6d6e5328c3d1` or revoked live `3060-thao`.

## Next concrete steps

1. After Quang online: fresh C: >=20 GB decimal, check candidate6 source/runtime, run
   `HETEROES_GPU_ACCEPTANCE=1 ~/.local/bin/heteroes-worker selftest --device cuda`. The installed launcher
   points at the correct home. For custom WSL Python probes use packaged `worker_environment()` to select
   matching PTX/JIT libraries; manual `LD_LIBRARY_PATH=/usr/lib/wsl/lib` previously caused a segfault.
2. Start both CLI agents on candidate6 (`~/.local/bin/heteroes-worker run`) with GPU acceptance env on
   Quang and `CUDA_VISIBLE_DEVICES=''` for Thao CPU. Thao home `~/.local/share/heteroes-c4-cpu`, Quang home
   `~/.local/share/heteroes-worker`. Verify actual process identities. Switch contribution ON for every
   current boot, including both desktops, via local Worker controls and current-boot lab API as needed.
3. Fresh run is predeclared in `docs/evidence/2026-10-21-long-multimachine-run-candidate6/README.md`.
   Scratch `.scratch/r11-long-run3/` has spec/rows/reward/run-thao.sh; copy to Thao `/tmp/heteroes-r11-long3`.
   It explicitly selects new runtime and all THREE correct GPU IDs; decoder is `hf_fp32_cpu_guard_v1`,
   new seed namespace, 50 generations/pop8/batch8/max32/antithetic/full/FP32/Python reward. Audit .05.
   Receive access token over stdin, never argv/output. Offer once; preserve new experiment/offer receipt.
4. Adapt detached monitor/snapshot/fault helpers from `.scratch/r11-long-run2` / `.scratch/r11-long-run`.
   Their OLD experiment IDs/paths/runtime choices are invalid for the new run. The old monitor merely
   logs and breaks on mismatch: the new one MUST also request experiment pause and drain/stop per plan.
   Fault around g20 while a main Quang candidate lease is active; guard exact agent/compute PID and
   process birth, stop both so auto restart cannot shorten outage; restart ~300 seconds later with
   proper launcher environment. Prove expired/failed attempt + successful retry from the ledger.
   Do not manufacture zero rewards or edit ledger/assignments/process ownership. Tests/mutation checks
   precede new behavior/helpers. No full monitor/fault helper for the new run has been created yet.
5. Collect a consistent private ledger/usage copy (NEVER commit leases/tokens). Run BOTH copied candidate
   and record/context verifiers on independent 5070 regeneration, require 50 generations/400 candidates,
   all texts/rewards/contexts/records/child hashes exact, zero mismatches, no quarantine, three GPU counts,
   usage + browser screenshot/no page errors. Any genuine mismatch => handoff/stop.
6. Windows uninstall acceptance; then FF main/push all (no force/tags/deletions; rejection => stop).
   Follow flag day approvals/backup/wipe/deploy/publication/device approvals/live smoke exactly in plan.
   Finally consolidate HANDOFF/archive old handoffs and update memory/backlog.

## Windows diagnostics and operator gotchas

Initial GPU self-test action returned ACTION_FAILED, no exception stack preserved. Two subsequent
self-tests pass (one process-only diagnostic wrapper, one normal), and the independent installed-runtime
nine-case CPU guard probe passes. The first failure remains unexplained; evidence is retained, no source
fix or causal diagnosis claimed. Track recurrent failures before release; do not suppress them.

`.scratch/windows-system-finish/action.py` controls the packaged app via private CDP driver. Private
researcher/args files already exist on Windows; never print them. `run-ps.py` sends encoded PS via SSH.
`action.py launch` can evaluate inspector before Node bootstrap: guard `typeof process !== 'undefined'`
before `process.mainModule` in future helper use. Existing `Start-Process -Wait` also waits descendants,
so a launch driver may keep the remote PS/local SSH waiting until app quits, even after driver exits.
One such private launch-control session remains waiting; actual app relaunch and separate status pass.
Do not kill the app to tidy this helper. Driver wrappers were restored; product source unchanged.

Native probe private inputs: `D:\HeteroES-r11-cpu-guard-probe-20261021` (includes ~943 MiB verified
parent). Local originals `.scratch/r11-audit-investigation/`; no model/parent blobs committed.
Current installed Windows profile runtime `D:\HeteroES-Worker-data\runtimes\41bf2c06ec02`.

Isolated Lab Server driver `.scratch/isolated-lab/start-c6.sh`, port8790, log `server-c6.log`;
5070 driver `.scratch/isolated-lab/worker5070/start-c6.sh`, log `app-c6.log`;
private installer HTTP8802 on tailnet, log `.scratch/r11-audit-investigation/candidate6-private-http.log`.
Private server/Worker XDG state stays under `.scratch/isolated-lab/`; no public controller restart.
Use fresh process inspection rather than old PID files. Do NOT use broad old stop scripts or pkill.
