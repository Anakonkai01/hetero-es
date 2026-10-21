# Candidate8 final acceptance: member restart, join/leave/rejoin, stale result (predeclared)

2026-10-21 Asia/Ho_Chi_Minh. Build `lf1-20261021-r11-candidate8` (the bytes meant for release). Written and committed
BEFORE the run. It carries the member-restart fix `98dd705` (ADR-009 item 8) on top of candidate7. Devices:
`../2026-10-21-candidate8-device-upgrades/` (written after the install). Package receipts: `../2026-10-21-r11-candidate8/`.

**About candidate7:** the candidate7 run (`../2026-10-21-long-multimachine-run-candidate7/`) is **not verified**. Its
independent verifier was interrupted and, by owner decision (2026-10-21), not rerun. Nothing here relies on it.

## Configuration

- **Coordinator:** Thao WSL CPU `cli-2ffce4b7de39` (`--device cpu`, decoder `hf_fp32_cpu_guard_v1`).
- **Initial GPU workers (JOIN at generation 0):** 5070 Ti Linux desktop `desktop-906949218c43`, Thao native Windows 3060
  `desktop-9f9da13f0f82`, Quang WSL 3060 `cli-894b5d440398`.
- **Joining worker:** GTX 1660 SUPER CLI `cli-3e355c6e9e70`, through `POST /api/v1/experiments/{id}/workers`.
- **Run:** scheduler `greedy-tail` (lab default), Qwen2.5-0.5B-Instruct full weights FP32, antithetic population 8,
  **50 generations**, batch 8, max 32 tokens, sigma .025, alpha .005, zscore@1, Python distinct-characters reward
  (`reward.py`), managed audit rate .05. Seed namespace `r11-candidate8-final-20261021` (new). Inputs: `spec.json`,
  `rows.json`, `run-thao.sh` (token via stdin, never argv).
- Contribution ON for every current boot before the offer, including the idle 1660S.

## Declared events

The operator monitor (`operator/monitor.py`; 8 tests, 21/21 mutants killed: `operator/test_monitor.py`,
`operator/mutate_monitor.py`) performs each event once, by applied generation, and only after the previous one has
recovered or its deadline passed. An event that cannot start before its last generation is recorded as
`not_exercised` and does **not** count as passed.

| # | Event | Earliest / latest generation | The system must then show |
| - | ----- | ---------------------------- | ------------------------- |
| 1 | 1660S JOIN | g10 | JOIN in the ledger; its results only inside its member windows |
| 2 | Hard stop of the whole Thao Windows Worker app while it holds a main lease (`fault-windows.ps1`, PIDs and start times recorded); relaunch after ~240 s (above the 120 s lease); contribution ON for the new boot | g14 / g23 | an `expiry` row; **`worker_restarted` with launch >= 1 in `lifecycle.jsonl` by itself** (no add/remove by the operator); a committed result leased after the restart |
| 3 | 1660S LEAVE | g28 | LEAVE; it stops |
| 4 | `kill -9` of Quang's `run_worker.py` only (`worker_proc.py kill`); the device agent stays up | g32 / g39 | an `expiry` row; `worker_restarted` launch >= 1 by itself; a committed result leased after it |
| 5 | 1660S JOIN again | g38 / g43 | second JOIN; a result inside the second window |
| 6 | `SIGSTOP` of the 5070's `run_worker.py` while it holds a lease, ~180 s (a timer sends SIGCONT after 330 s at the latest), then `SIGCONT` | g40 / g43 | an `expiry` row for it; its late result is not committed after a later attempt; exactly one committed result per candidate |

**Restart stop rule:** if events 2 or 4 produce no `worker_restarted` plus a new committed result within **10 minutes**
(after contribution ON for the Windows app, after the kill for Quang), the monitor records a `failed` verdict. The run
goes on to 50 generations, nothing is repaired by hand, and the session stops with a handoff for a stronger model.

**Event 6 outcomes, declared before the run.** Accepted: (a) the late result is rejected/ignored and a later attempt
commits; (b) the late result is accepted only if no later attempt had committed. Not accepted: two committed results for
one candidate, a result of an expired attempt committed after a later attempt, a ledger error or halt. How the worker
reacts after SIGCONT is recorded, not a criterion.

## Required acceptance

- COMPLETED with exactly 50 applied generations and 400 committed candidate results; zero audit mismatches, no
  quarantine, at least one completed audit. Any mismatch or quarantine: the monitor requests PAUSE; stop, handoff.
- `elastic_checks.py` (in `verify-records.py`): `membership_violations == []`; the 1660S changes are exactly
  JOIN, LEAVE, JOIN (strictly increasing effective generations) with results inside, and at least one in each, window;
  explicit `expiry` rows for Windows, Quang and the 5070, none of those attempts committed, each candidate committed by a
  later attempt; `worker_restarted` (launch >= 1) with no manual membership change and a later committed result for
  Windows and Quang; one committed result per candidate (400 rows, 400 distinct).
- Independent 5070 Ti regeneration with a separate cache (`verify_managed_run.py` then `verify-records.py`): every
  candidate text/hash/reward, every generation context and record, and all 50 child hashes exactly equal.
- Controls: `negative.py` on a scratch copy of a finished run's ledger (a positive control with a synthetic lifecycle line
  and nine tampered copies, each failing for its own reason) must behave as declared.
- Usage receipt and a browser screenshot of the experiment page without page errors.

## What this does NOT show

This folder is a predeclaration, not a run, outage, recovery, parity or release pass. No learning, speedup, arbitrary
model or universal cross-GPU numerical claim; the .01 near-tie guard is empirical. No deployment, publication, merge or
push is authorized; each irreversible flag-day action still needs the owner's explicit "đồng ý". The run covers one
configuration of five machines; a coordinator or lab-server crash during a run is not part of it (see
`../2026-10-19-v3-recovery/`).
