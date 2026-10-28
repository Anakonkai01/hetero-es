# Attempt 1: operator-interrupted, not acceptance

Experiment `8486e06b2d1f481399decd9ef50f7f5e`, 14 applied generations, 112 committed candidates,
10 matched audits, no audit mismatch or quarantine observed. Quang 20 commits, 5070 Ti 35,
Thao Windows 57. Planned generation-20 fault was not injected. No independent 50-generation parity.

First pause after generation 10 moved Thao large artifacts to D:; initial copy validation rejected
concurrent cloud-sync retention changes and preserved the source. After graceful CLI shutdown, rsync
and full SHA256 comparison passed (`relocation.json`); only artifacts moved, ext4 state/runtime stayed.

Second pause was caused by an operator's premature diagnosis of replay_failed. Code and the 5070 Ti
log show the expected full-sync fallback: 988065536 bytes downloaded in 146.507 s, then verified replay
of three updates. Quang was still downloading (349175808 bytes observed), not failing numerics.
The original stop classification is explicitly retracted in append-only operator-events.jsonl.
The sync-only Quang compute PID was killed to finish abandoning this attempt; all four devices
confirmed stopped/unallocated before attempt 2. Coordinator CLI was gracefully stopped.

Receipts remain immutable. This is not evidence of a replay/recovery bug, a successful induced-fault
recovery, completed 50-generation correctness, or live/release readiness. Continue with attempt 2.
