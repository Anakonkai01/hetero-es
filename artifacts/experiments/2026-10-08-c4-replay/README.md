# C4 measured for real: replaying the recorded updates on each machine, 2026-10-08

**Written by the AI; the owner has not reviewed it.** Question (MASTER C4, EQ6): to bring a worker to the next generation's weights, is it better to transfer the weights (full synchronization, 988 MB) or to
REPLAY the update (apply the generation record: seeds, coefficients, alpha; 1.4 KB) with the worker's own GPU? Until now the replay cost was an extrapolation (STATUS 0.000000, "13 s against 10 s, not a run").
This folder is a run.

## What was done
`export_records.py` takes the 100 update records of the learning run `lrtA` (24 candidates each, CUDA noise engine) from its ledger, with the hashes of the 21 kept checkpoints, into `records-lrtA.json` (164 KB).
`replay_probe.py` runs on a machine: it loads the pinned base model (the generation-0 weights), applies the recorded update of generation 0, 1, ..., 99 in order (`apply_coefficients_cuda_`, the function the coordinator uses) and, after EVERY generation, compares the SHA-256 of all
weights with the child hash that the 5070 Ti stored in the ledger, and after every 5th with the kept checkpoint. The seconds of each update are CUDA-synchronized and exclude the hash.
Files: `replay-5070ti-lrtA.json/.log` (RTX 5070 Ti, torch 2.13.0+cu132), `replay-1660s-lrtA.json/.log` (GTX 1660 SUPER, torch 2.13.0+cu132, Python 3.14).

## Results (measured)
| | 5070 Ti | 1660S |
|---|---|---|
| updates replayed | 100 | 100 |
| ledger child hashes matched | **100 of 100** | **100 of 100** |
| checkpoint hashes matched | 20 of 20 | 20 of 20 |
| seconds per update (24 candidates), median (min - max) | 1.76 (1.74 - 2.12) | 12.27 (12.16 - 13.14) |
| seconds per candidate | 0.073 | 0.511 |
| size of the record | 1,371 bytes | 1,371 bytes |

**So the replay is exact across the two GPUs for 100 consecutive generations: no drift (0 of 100 differences), the weights after 100 updates are bit-identical on the machine that trained them and on the one that only replayed.**
This extends the earlier "same weights after one candidate" cross-machine checks to a whole 100-generation trajectory.

## Replay against full synchronization (1660S, N = 24)
Full synchronization of the same machine, measured in a 5-generation run of 07/10 night on the same cable (`smoke` run, worker log): transfer 8.55 s, load 0.51 s, rehash 0.6-1.1 s: **about 9.8 s**, and it does not depend on N.
Replay: **12.27 s**, and it grows with N (0.511 s per candidate). Bytes: 1.4 KB against 988 MB (about 720,000 times fewer).

| N | replay on the 1660S (0.511 s x N) | full sync (gigabit cable) |
|---|---|---|
| 8 | 4.1 s | 9.8 s |
| 19 | 9.7 s | 9.8 s |
| 24 | 12.3 s (measured) | 9.8 s |
| 32 | 16.4 s | 9.8 s |

Reading (arithmetic on the measured parts, not a separate run): on this gigabit cable replay is faster than synchronization only for N below about 19; at N = 24 synchronization is about 2.5 s (20 percent) faster. The balance depends on the network:
sync time is about 988 MB / bandwidth + 1.3 s, so replay at N = 24 (12.3 s) wins when the effective bandwidth is below about 720 Mbit/s (a Wi-Fi or a shared link): a 100 Mbit/s link would need about 80 s per sync against 12.3 s of replay.
A worker that is k generations behind catches up by replay in k x 12.3 s or by one sync in 9.8 s.

## What this does NOT show
- One pair of GPUs and one trajectory (24 candidates, CUDA engine, 100 generations of one run). The CPU engine was not replayed (its cost on the 1660S was 3.7 s per candidate in G6).
- The replay is a probe script, not a path of the worker runtime: nothing here makes a worker choose between replay and sync, and the sync figure comes from another run (same machine and cable), not from this one.
- The 5070 Ti's times were taken while other short jobs used the same GPU for part of the 100 updates (the spread is small: 1.74 - 2.12 s); the 1660S ran the probe alone.
- The numbers say nothing about a compressed delta synchronization (an idea in TODO), which would compete with both.
