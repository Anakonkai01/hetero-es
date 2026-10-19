# G6: the benchmark with the FP32 forward pass, N = 96 (07/10/2026)

As `../2026-10-07-g6-benchmark-fp32/` (same machines, software, `--eval-dtype float32 --chunk 16`, lease 60 s with heartbeat, coordinator update on 28 noise threads) with **N = 96 candidates and 3 generations per run, two repeats** of
B0x2, B3x2 and B4x2 (6 runs; the steady state is generations 1 and 2). It asks whether a longer candidate phase lets the 1660S do more: its fixed 10 s synchronization is then a smaller part of a generation.

| condition | T of a generation (s) | 95 % | speed-up over B0x2 | 95 % | candidates (wait) | update |
|---|---|---|---|---|---|---|
| B0x2 (two processes on the 5070 Ti) | 96.5 | 3.4 | 1.000 | | 68.7 s | 28.1 s |
| B3x2 (+ the 1660S, greedy) | 94.0 | 17.1 | 1.026 | 0.190 | 65.5 s | 28.3 s |
| B4x2 (+ the 1660S, tail-aware) | 93.1 | 3.8 | 1.036 | 0.056 | 64.5 s | 28.2 s |

All 6 runs ended with the same rewards and the same weights hashes. The gain of the tail-aware policy at N = 96 (3.6 percent) is of the same size as at N = 24 (2.4 percent) and, with two repeats, its interval includes 1.0 (1.036 +- 0.056);
greedy is not distinguishable from nothing (1.026 +- 0.190). The update is now 28 s of a 94 s generation (96 x 0.29 s of CPU noise): a part that the second GPU cannot help with and that grows with N like the candidate phase does, so the share of the
generation that the 1660S can shorten does not grow with N. This is the bound of the pair, not of the system: a GPU 5 times slower adds at most about a fifth of the fast one's candidate throughput, and the update does not shrink.

Not shown: more repeats (two), other N, a longer rollout.
