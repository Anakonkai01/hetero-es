# Candidate7 managed acceptance: greedy-tail, mid-run join/leave, hard stop (predeclared)

2026-10-21 Asia/Ho_Chi_Minh. Build `lf1-20261021-r11-candidate7`, source `63d9b0a`, Worker runtime
`57b0faf6d31a394afef5fd4760f1d0da6ebbe4e922dce5fb9eea392917c3adc7`. Replaces the candidate6 predeclaration
`../2026-10-21-long-multimachine-run-candidate6/`, which never started. Devices: `../2026-10-21-candidate7-device-upgrades/`.

**Owner choice (2026-10-21, in chat):** Quang is offline, so the g20 hard stop targets **Thao's native Windows 3060**
instead. Quang takes no part.

## Configuration

- **Coordinator:** Thao WSL CPU `cli-2ffce4b7de39`.
- **Initial GPU workers:** 5070 Ti Linux desktop `desktop-906949218c43`, Thao Windows 3060 `desktop-9f9da13f0f82`.
- **Joining worker:** GTX 1660 SUPER CLI `cli-3e355c6e9e70`, added through `POST /api/v1/experiments/{id}/workers`.
- **Run:** scheduler `greedy-tail` (the lab default; `--lab` cannot override it), `allowJoin` false. Qwen2.5-0.5B-Instruct,
  full weights, decoder `hf_fp32_cpu_guard_v1`, FP32, antithetic population 8, 50 generations, batch 8, max 32 tokens,
  sigma .025, alpha .005, zscore@1, Python distinct-characters reward (`reward.py`), managed audit rate .05.
  Seed namespace `r11-candidate7-greedytail-elastic-20261021` (new). Exact inputs: `spec.json`, `rows.json`,
  `run-thao.sh` (the access token comes through stdin, never argv).
- Contribution ON for every current boot before the offer, including the 1660S, which stays idle until it joins.

## Declared events (operator monitor, `.scratch/r11-c7-run/monitor.py`, logic tested with 10/10 mutants killed)

1. At ≥ g10 applied, add the 1660S. It takes effect at a generation boundary and is recorded in the ledger.
2. At ≥ g19 applied, while Thao Windows holds an active main lease: hard-stop every process of the Windows Worker
   app and its candidate7 runtime (`fault-windows.ps1`; PIDs and start times are recorded). After ~300 s, relaunch it
   and turn contribution ON for the new boot.
3. At ≥ g30 applied, remove the 1660S.
4. On any audit mismatch or quarantine, the monitor requests PAUSE and stops (stop rule: handoff, no retry).

## Required acceptance

- COMPLETED with exactly 50 applied generations and 400 candidate results; zero audit mismatches, no quarantine,
  at least one completed audit.
- Membership: `membership_violations == []`; the ledger holds exactly one JOIN and then one LEAVE of the 1660S, and the
  1660S committed results only in the generations between them (at least one).
- Failure: explicit `expiry` rows for Thao Windows attempts, each candidate then committed by a later attempt. Never
  inferred from logs, never a synthetic zero reward.
- Independent 5070 Ti regeneration with a separate cache: every candidate text/hash/reward, every generation context
  and record, and all 50 child hashes exactly equal (`verify_managed_run.py`, then `verify-records.py --joiner
  cli-3e355c6e9e70 --failed-worker desktop-9f9da13f0f82`). A negative control must make the elastic check fail.
- Usage receipt and a browser screenshot of the experiment page without page errors.

## What this does NOT show

This folder is a predeclaration, not a run, outage, recovery, parity or release pass. No learning, speedup, arbitrary
model or universal cross-GPU numerical claim; the .01 near-tie guard is empirical. Quang is not covered. No deployment,
publication or approval is authorized; each irreversible flag-day action still needs the owner's explicit "đồng ý".
