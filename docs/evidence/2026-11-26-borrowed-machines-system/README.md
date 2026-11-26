# 2026-11-26 — system checks with the borrowed machines back (midday)

Machines: `5070ti-nhan` (lab, coordinator and worker, RTX 5070 Ti, Linux), `5070ti-nhut` (RTX 5070 Ti, Linux, another
city), `3060-thao` (RTX 3060, WSL2). The second RTX 3060 (`3060-quang`) was offline, so no 4-GPU configuration.
All lab runs used the deployed worker runtime `3f1adea02535` (bundle `20261126-872152cf`). Private addresses and the
borrowed machine's user name are replaced by `<tailnet-ip>`, `<nhut-ssh>` and `<nhut-user>` in the copies here.

## 1. Llama-3.2-1B strict parity on the RTX 3060 (`llama32-parity/`)

`acceptance/probes/strict_parity.py --gpu --model llama32` (commit `099f20da` sources, runtime `9a553d2dfae9` Python)
on the RTX 3060 under WSL2, compared with `acceptance/golden/strict-b22-llama32.json` recorded on the RTX 5070 Ti
(see `2026-11-26-llama32-parity-and-backup-interval`): `status ok`, no mismatches, 92.6 s. SM86 and SM120 give the same
tokens, hashes of parent/± candidates, restore and EOS stop for Llama 3.2 (RoPE `llama3`) as for Qwen.

## 2. Speed on 1, 2 and 3 GPUs (`speed/`)

E4 configuration (Qwen2.5-1.5B continued model after E4 segment 1, Countdown, population 32, 384 tokens,
`strict_b22_v1`, recovery point every 10 generations), driven by `speed_multi.py`; `speed_table.py` computes the
per-step medians/means from the coordinator's events (validation generations excluded).

| Configuration | Run | Generations | Scoring median | Generation median / mean (s) | vs 1 GPU (median / mean) | Audits |
| --- | --- | --- | --- | --- | --- | --- |
| 1 × 5070 Ti (night 26/11) | `6131a0ad` | 15 | 83.5 | 102.5 / 106.1 | 1.00 | — |
| 2 × 5070 Ti | `bc2b12ef` | 11 | 52.9 | 71.2 / 69.6 | 1.44 / 1.52 | 22/22 |
| 2 × 5070 Ti + 3060 | `9ce75c6f` | 11 | 50.6 | 69.9 / 74.7 | 1.47 / 1.42 | 21/21 |

Per device on 3 GPUs (medians over generations): 5070 Ti 12–13 s to the first candidate, 2.6–2.7 s per candidate,
~14 candidates per generation; RTX 3060 28 s, 7.3 s, 3.4 candidates. Adding the 3060 does not shorten a generation.

## 3. Live fault demo (`fault-demo/`)

Run `94d9b883` (2 × 5070 Ti, 16 generations). `fault_controller.py` acted on `5070ti-nhut` at generation boundaries
(`fault-actions.jsonl`): generation 3 `systemctl --user kill -s KILL heteroes-worker` (crash), generation 8
`heteroes-worker off`, generation 11 `heteroes-worker on` + `POST /api/v1/experiments/<id>/workers {"action":"add"}`.
The lab page was recorded meanwhile (`recording-chapters.json`; the edited 2-minute video is in the report folder).

- Crash: the lease expired and the candidate was redone by the other GPU; systemd restarted the worker, which rejoined
  after ~50 s and worked from generation 4 (including audits). Generation 3 took 102 s.
- OFF: LEAVE applied at the generation-9 boundary; generations 9–11 ran on one GPU.
- ON + add: JOIN applied at generation 12 (`worker_joined`, `rejoin: true`), but the worker held only the base weights,
  its replay chain was longer than 8 updates, and the full 3 GB sync took 799 s (`nhut-worker-rejoin-events.jsonl`), so
  it scored nothing before the run ended.
- Run COMPLETED 16/16, audits 12/12 matched.
- Finding: generations 8, 12 and 13 took 214–237 s because the drain waited for an audit until its timeout
  (`audit_incomplete reason=timeout` in `coordinator-events.jsonl`) while no other worker was asking for work. Fixed in
  `83480c6d` (drain closes as `insufficient_workers` after 30 s without a possible auditor). E4 (25/11) has no timed-out
  drain (5 `insufficient_workers` closures only), so its numbers are unaffected.

## 4. Finished-run cleanup on real data (`cleanup/`)

The repository code (`run_cleanup.apply`) was run by hand on this coordinator (the deployed runtime does not have it).
`bc2b12ef`: removed, receipt said 27.79 GB but the disk gained ~15 GB (hard links kept alive by a link outside the
removed directories) → fixed in `099f20da`. `94d9b883`: receipt 18.53 GB, disk gained 18.53 GB. Both receipts name
the READY lab point (final, generation 11 and 15) the run relies on.

## 5. Fault demo again with the fix deployed, and automatic cleanup (`fault-recheck/`)

Evening 26/11 the owner published worker `20261126-83480c6d` to the lab downloads page; `5070ti-nhan`, `5070ti-nhut`
and `3060-thao` updated to runtime `01446be01907` (self-test passed on each). The same scenario as section 3 was rerun
(run `f8700fc5`, 2 × 5070 Ti, 16 generations, crash at 3, OFF at 8, ON + add at 11).

| | `94d9b883` (old runtime) | `f8700fc5` (fixed runtime) |
| --- | --- | --- |
| Audit drains closed by `timeout` | 4 (gens 8, 12, 13, 15) | 0 |
| Audit drains closed by `insufficient_workers` | 3 | 7 |
| Generation 8 / 12 / 13 (s) | 215 / 228 / 237 | 110 / 138 / 138 |
| Audits matched | 12/12 | 15/15 |

`fault-compare-before-after.json` is `fault_compare.py 94d9b883 f8700fc5` on the coordinator's events. The remaining
extra ~30 s over a one-GPU generation (~100 s) is the new idle threshold. The rejoined worker again needed the full
3 GB sync (1,113 s, `nhut-worker-rejoin-events.jsonl`) and scored nothing before the end: the known limitation.

Automatic cleanup, first time on the lab without anyone running it: the run ended 17:50; ~15 minutes later the
coordinator's sync loop removed 18.53 GB (`local-cleanup-automatic-f8700fc5.json`, relying on the READY final point,
generation 15); free space went from 15 to 32 GiB.

## What this does NOT show

- No 4-GPU measurement with the recovery point every 10 generations; the 2- and 3-GPU numbers are 11 generations each,
  with the same training batches but different noise per run, so differences below ~5 s are not meaningful.
- The audit fix and automatic cleanup were checked once each on the lab (section 5), not over many runs.
- The fault demo is one run with one machine taken away; it does not cover the coordinator machine failing, network
  partitions, or more than two workers.
- The Llama parity covers the probe's 64 chat rows and cases, not every input; it is not part of the 37-pair matrix.
- Nothing here is a learning result.
