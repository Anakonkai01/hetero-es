# Candidate9 restart run: one fault at a time, each member must come back by itself (predeclared)

2026-10-21 Asia/Ho_Chi_Minh. Build `lf1-20261021-r11-candidate9`. This file was written and committed BEFORE the run.
Candidate9 is candidate8 plus the fixes for the two reasons candidate8 restarted nobody
(`../2026-10-21-c8-restart-causes/`). CPU gate: `../2026-10-21-r11-candidate9-checks/` (23/23). Package and device receipts are
written after the build and install.

## Why this run

On candidate8 the run itself was exact, but member restart failed on real machines. Thao Windows looped on a refused
qualification. The rejoined 1660S was released by the lab a second time. The Quang `kill -9` was never exercised.
This run checks only the restart paths. The faults come one at a time, each with its own 10-minute deadline, so
one late verdict cannot block the next fault. The `SIGSTOP` stale-result event passed on candidate8, and this fix does
not touch leases, expiry or commit, so it is left out.

## Configuration (as candidate8, new seed namespace)

- **Coordinator:** Thao WSL CPU `cli-2ffce4b7de39` (`--device cpu`, decoder `hf_fp32_cpu_guard_v1`), `run-thao.sh` (token
  via stdin; refuses to start unless the installed supervisor has `worker_restart_deferred`).
- **Initial GPU workers:** 5070 Ti Linux desktop `desktop-906949218c43`, Thao native Windows 3060
  `desktop-9f9da13f0f82`, Quang WSL 3060 `cli-894b5d440398`. **Joining worker:** GTX 1660 SUPER `cli-3e355c6e9e70`.
- **Run:** Qwen2.5-0.5B-Instruct FP32 full weights, antithetic population 8, **50 generations**, batch 8, max 32 tokens,
  sigma .025, alpha .005, zscore@1, Python distinct-characters reward (`reward.py`, `rows.json`), scheduler `greedy-tail`,
  audit rate .05. Seed namespace `r11-candidate9-restart-20261021` (`spec.json`).
- Contribution ON for every current boot before the offer, including the idle 1660S.

## Declared events (`operator/monitor.py`; 6 tests, 24/24 mutants killed: `operator/mutation.log`)

The monitor reads the coordinator ledger every 10 s and performs each event once. **A fault starts only after the
previous fault has a verdict (recovered or failed).**

| # | Event | When | Must then show, within 10 min |
| - | ----- | ---- | ----------------------------- |
| 1 | 1660S JOIN | g >= 2 | JOIN in the ledger |
| 2 | `kill -9` of Quang's `run_worker.py` only (`worker_proc.py kill`); the agent stays up | g >= 5, while Quang holds a lease (not exercised if not started by g20) | `worker_restarted` for Quang (launch >= 1) after the kill, then a new committed Quang result |
| 3 | 1660S LEAVE, then JOIN again once the LEAVE is effective in the ledger and that generation is applied | after verdict 2 (not exercised if not done by g30) | `worker_restarted` for the 1660S after the second JOIN, then a new committed 1660S result (inside its second window) |
| 4 | Hard stop of the whole Thao Windows Worker app while it holds a lease (`fault-windows.ps1`); relaunch after 240 s (`launch-c9.ps1`); contribution ON for the new boot | after verdict 3 (not exercised if not started by g36) | the app stays up with ONE boot (no new `bootId` loop), `worker_restarted` for Windows after contribution ON, then a new committed Windows result |

**Stop rule:** a `failed` verdict on any of events 2-4 ends acceptance for this candidate. The run goes on, nothing is
repaired by hand, and the session stops with a handoff. A `not_exercised` event is not a pass.

## Required acceptance

- COMPLETED, 50 applied generations, 400 committed results, 0 audit mismatches, no quarantine, at least one audit.
- Verdicts `recovered` for events 2, 3 and 4 (`operator-events.jsonl`).
- `verify-records.py … --joiner cli-3e355c6e9e70 --joiner-changes JOIN,LEAVE,JOIN --expiry-workers
  cli-894b5d440398,desktop-9f9da13f0f82 --restart-workers cli-894b5d440398,desktop-9f9da13f0f82`: no membership
  violation, 1660S results only inside its windows and in each window, explicit expiry rows for Quang and Windows (each
  fenced and committed by a later attempt), system restarts with later results for Quang and Windows, one result per
  candidate. The 1660S restart is checked through its second-window result plus its `worker_restarted` event, because
  its JOIN/LEAVE are deliberate membership changes.
- Independent 5070 Ti regeneration (`verify_managed_run.py`, then `verify-records.py`): all candidate texts, rewards,
  contexts, records and 50 child hashes exactly equal.
- Controls: `negative.py` on a scratch copy of this run's ledger, as for candidate8.
- `lifecycle.jsonl` of the coordinator is kept. Every `worker_restart_deferred` line is reported with its HTTP status.

## What this does NOT show

This is a predeclaration, not a result. One configuration of five machines, one occurrence of each fault. There is no
claim about learning, speed, arbitrary models or universal cross-GPU equality. There is no coordinator or lab crash, no
stale-result recheck, no publication, deployment, merge or push. The release flag day still needs the owner's explicit
"đồng ý" at each irreversible step.
