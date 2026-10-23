# Handoff: STOP at candidate5 long-run audit mismatch — 2026-10-20

Read `../AGENTS.md`, `plan-r11-release.md` and
[evidence/2026-10-20-long-multimachine-run-attempt2/RESULTS.md](../../evidence/2026-10-20-long-multimachine-run-attempt2/RESULTS.md).
This supersedes the operational state in `handoff-2026-10-20-quang-then-long-run.md`.
Branch `feat/v3-audit-recovery`; main remains **086c282**. No source/runtime/backend/frontend/desktop code was
changed relative to the starting commit 35603d4. This continuation changed operational test state and documentation only.

## Why work stopped

The plan requires handoff on an unexplained audit/parity mismatch. This is a real ledger audit row with
`matched=0`, not a failure-looking log message. No fix was attempted and no further GPU computation is authorized
by this continuation after the stop. Resume investigation under the owner's next instruction.

- Experiment: **e07deeb168ae4baaba3ac770b89043a6**, status PAUSED, **13/50 generations**, 104 committed candidates.
- **4 audits, 1 mismatch, no quarantine.** The pending/in-flight work drained before the pause completed.
- Candidate **g10/c5**, generated on 5070 Ti, audited on Quang WSL 3060.
- Committed hash **519e5172210e0b97dfc20a761c97caa4635056912d67f6120afb52213fca8471**.
- Audit hash **42c3204f4d1ed47de9bf73e463ec5333b3587763134e478b65ae9d55ac589dab**.
- Parent **dfbfa65cae82010b068371455d4462b6ad88572788c784d5b5a3f2a52b3a93d9**;
  both worker traces show verified replay to this hash before their respective step.
- Audit timestamp (coordinator): **2026-10-20 14:55:08.626002 UTC**.
- The generation-20 kill and five-minute return were **not reached**; independent 50-generation parity was not run.

This does not establish a root cause. Same parent hash narrows investigation but does not rule out context/seed/sign,
audit scheduling or decoding issues. Full audit text was not persisted, only its reported hash; original completion
texts and the exact descriptor/context/update are preserved in the evidence. Keep the numerical contract intact.

## Completed Quang / step 4

Candidate5 install finished when this continuation began. CUDA self-test passed on RTX 3060 with
`LD_LIBRARY_PATH=/usr/lib/wsl/lib` and `HETEROES_GPU_ACCEPTANCE=1`, then pairing and admin approval in the isolated lab
succeeded. Device **c2db3633fe9d4edbb790881469d6dacb**, worker **cli-894b5d440398**. C: stayed approximately 20 GiB free.
Receipt: `evidence/2026-10-20-long-multimachine-run/quang-qualification.json`; its cached join descriptor still says PENDING,
whereas `final-lab-state.json` contains the authoritative live APPROVED status. Memory is readable and key-based SSH
worked; no access grant is needed. Credentials were neither printed nor copied.

## Two test attempts, both preserved

1. `8486e06b2d1f481399decd9ef50f7f5e`: 14 generations, 10 matched audits. Operator interrupted it to relocate the
   coordinator's growing large artifacts off Thao C:, then mistakenly paused on a normal `replay_failed` fallback.
   The stop classification was retracted after verifying the 5070 Ti completed a full sync. Quang's sync-only compute
   process was killed to abandon this interrupted attempt, all allocations released, coordinator CLI stopped.
   This was not the planned generation-20 fault and is not release acceptance. Details in the first attempt's RESULTS.md.
2. `e07deeb168ae4baaba3ac770b89043a6`: fresh spec namespace `r11-candidate5-long-3gpu-20261020-attempt2`, all three GPUs
   working from generation 0, no operator pause/restart before the audit mismatch. This is the genuine stop condition.

Storage relocation preserved SHA256 identity of every current source file. An initial copy validation rejected
cloud-sync retention changes while compute was paused; the source remained intact. The successful relocation stopped
the coordinator CLI first, rsynced and hash-compared all files before replacing only `artifacts` with a D: symlink.
Runtime, settings, process records and live ledger remain on WSL ext4. Do not repeat a live-artifact move merely after
pausing computation: the agent's cloud-sync thread can continue mutating/pruning recovery sidecars.

## Preserved artifacts / restart information (do not restart a GPU run automatically)

- Local private copy: `.scratch/r11-long-run2/private-run-copy/` — consistent ledger and usage backups, recipe, plan,
  dataset and split JSONLs, state/runner and lifecycle/events. SQLite files contain leases: never print or commit them.
- Thao original: `~/.local/share/heteroes-c4-cpu/agent-state/runs/e07deeb168ae4baaba3ac770b89043a6`.
  Large data: `/mnt/d/HeteroES-r11-long-data-20261020/artifacts/coordinators/e07deeb168ae4baaba3ac770b89043a6`.
  Keep parent/child weight files and current recovery points. No operator weight cleanup was done.
- Worker assignment for attempt 2 is recorded in each curated `*-worker-events.json`; original worker directories are
  `agent-state/workers/<assignmentId>/r0`. Linux desktop state is under
  `.scratch/isolated-lab/worker5070/xdg/config/@heteroes/worker/`; Quang's CLI home is `~/.local/share/heteroes-worker`.
- CLI offer scripts/specs and collector are private in `.scratch/r11-long-run2/` and Thao `/tmp/heteroes-r11-long2/`.
  The background monitor PID 2553495 exited on STOP_AUDIT, before its fault injection. No fault injector remains running.
- Copied `verify_managed_run.py` is the historical candidate tool: it compares candidates/rewards/children but applies
  stored update inputs and does not enforce an expected generation count. Before claiming full acceptance, also rebuild
  every context/update record and require 50 generations. A supplemental analysis script is prepared at
  `.scratch/r11-long-run/verify-records.py`; its historical two-generation CPU control passed and a corrupted reward was
  rejected. It was not used for current-run acceptance; no GPU parity was run after this stop.

## Final devices and services

All four devices contribution **OFF**, unallocated, original processes confirmed stopped in the managed paused state:

| Role | Worker | Device |
|---|---|---|
| 5070 Ti desktop | desktop-906949218c43 | 5e1b71846ce4404b9d919ec87023dd78 |
| Thao Windows 3060 | desktop-9f9da13f0f82 | 8f3d691978e24167a257f018643f9165 |
| Quang WSL 3060 | cli-894b5d440398 | c2db3633fe9d4edbb790881469d6dacb |
| Thao WSL CPU coordinator | cli-2ffce4b7de39 | 47e0546da4464ca484a20768ce19aca6 |

Thao coordinator CLI PID **11590** and Quang CLI PID **1432** were gracefully stopped and are absent.
The isolated Lab Server (8790), Linux desktop Worker and Thao Windows desktop Worker remain running idle/OFF.
Their existing start/action helpers remain available. Windows contribution-args.json was set to false on both sides;
set it to true explicitly for a future authorized test. The private installer HTTP server PID **2143087** on 8801 remains
unchanged. Thao's original `worker-system-finish-backup` is untouched. Free space: Thao C: ~10 GiB, D: ~818 GiB;
Quang C: ~20 GiB. The public lab and its published r10 installers were untouched.

## Next work for the stronger model

1. Investigate the exact g10/c5 mismatch using the preserved descriptor, context, reward/scorer, manifest, both verified
   parent traces and actual seed/sign. Distinguish an audit/context race from GPU greedy-decoding near ties or another
   numerical issue; the latter is a known historical risk, not an established explanation for this failure.
2. With the owner's next instruction, reproduce only the failing candidate on the two devices, retain both text arrays,
   and compare the first divergent token/logits if needed. Do not start another long/learning run to diagnose it.
3. Follow tests-first and scratch mutation checks for any approved fix; obey the frozen numerical contract. A behavior
   fix requires a new candidate build and renewed device acceptance, not silently patched candidate5 packages.
4. Repeat step 5 as a fresh declared 50-generation managed acceptance, with actual audits, real generation-20 outage,
   successful retry, independent regeneration of all candidates, 50 contexts/records/child hashes and usage/browser proof.
5. Then finish Windows candidate5 (or replacement candidate) quit/relaunch/uninstall, step 6 ff merge/push, step 7 live
   flag-day confirmations, and step 8 full documentation consolidation/memory. None of those gates was completed here.

Other previously planned difficult follow-ups remain: CLI offer duplicate-draft idempotence; publisher alias/manifest
window; the two SECURITY-NOTES policy decisions; Windows CPU coordinator acceptance; 1660S. Do not confuse those with
this new release-blocking audit mismatch. No push/merge/tag/publication/deployment occurred in this continuation.
