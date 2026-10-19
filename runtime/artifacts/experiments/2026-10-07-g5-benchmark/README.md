# G5: B0, B1, B2, B3 with three repeats each, N = 8 and N = 24 (07/10/2026)

24 runs of `scripts/run_benchmark.py` (3 generations each, experiment id `g5`, alpha 1e-3, sigma 1e-3, chunk 1 everywhere), the 5070 Ti holds the coordinator and a
worker, the 1660S a second worker over the direct cable. The numbers come from `scripts/summarize_benchmark.py` (`summary-n8.*`, `summary-n24.*`); the raw logs of every run are in
the `n<N>-<condition>-r<k>/` folders (coordinator ledger and events, one JSONL per worker). The predictions (`prediction-n*.json`) were written **before** the runs, from
`../2026-10-07-g4-profiles/profile-5070ti-v2b.json` and `profile-1660s-v2.json`, with the fixed part of the update cost (10.2 s) taken from the G4 runs (so it is calibrated on
earlier runs, not predicted blind). The repeats go round the conditions (r1 of B0, B1, B2, B3, then r2 ...), one run at a time, nothing else running on the machines.
Conditions: **B0** the 5070 Ti alone (the fastest GPU), **B1** waves of two, **B2** quotas by measured speed, **B3** greedy. **H0 is not run as a separate condition: with the v2 profiles both safe chunks are 1, so sizing does nothing, and the admission decides "do not admit the 1660S" at N = 8 (H0 = B0) and "admit" at N = 24 (H0 = B3); H0 has no result of its own** (MASTER section 9: merge and say so).
T = mean time of one generation; the three numbers after it are the spread of the three repeats (each a mean of 3 generations).

## Results

| N | condition | T (s) | min - max | wait for candidates | update | ClusterBenefit | DeltaT (s) | predicted T | error |
|---|---|---|---|---|---|---|---|---|---|
| 8 | B0 fastest alone | 85.2 | 83.4 - 86.3 | 39.7 | 44.8 | 1.000 | 0 | 81.0 | -5.0% |
| 8 | B1 static wave | 127.7 | 125.7 - 128.9 | 82.6 | 44.5 | 0.667 | -42.5 | - | - |
| 8 | B2 static proportional | 92.9 | 91.2 - 95.6 | 49.5 | 42.7 | 0.918 | -7.6 | 100.6 | +8.3% |
| 8 | B3 greedy | 84.3 | 82.0 - 85.8 | 39.9 | 43.8 | 1.011 | +0.9 | 83.6 | -0.9% |
| 24 | B0 fastest alone | 223.8 | 220.8 - 226.2 | 112.2 | 111.0 | 1.000 | 0 | 221.3 | -1.1% |
| 24 | B1 static wave | 341.3 | 336.9 - 345.3 | 218.2 | 122.4 | 0.656 | -117.5 | - | - |
| 24 | B2 static proportional | 216.1 | 209.2 - 222.9 | 100.5 | 114.9 | 1.036 | +7.7 | 219.4 | +1.5% |
| 24 | B3 greedy | 216.3 | 213.5 - 218.8 | 100.9 | 114.7 | 1.035 | +7.5 | 203.2 | -6.0% |

Candidates per generation of the 1660S / the 5070 Ti: N = 8: B1 4 / 4, B2 2 / 6, B3 1.3 / 6.7; N = 24: B1 12 / 12, B2 5 / 19, B3 5 / 19 (B0: 0 / N). The 1660S spends 35 s per run on
two synchronizations (17.5 s each: transfer 8.6, load 4.1, rehash 4.8; generation 0 needs none) and is idle 13 to 15 s of the waiting time; the 5070 Ti is idle 489 s per B1 run at N = 24
(it waits for the 1660S at every wave), 43 s in B3 and B2, 9 s alone.

**All 12 runs of N = 8 and all 12 of N = 24 gave exactly the same rewards and the same weights hash** (`consistent` in the summaries): whoever evaluated a candidate, the generation
ended the same. B3 and B2 had the 1660S evaluate 4 to 15 candidates per run (264 evaluations in all), none differed from the 5070 Ti's value.

## What this shows

* **The fastest GPU alone is the baseline to beat, and the cluster beats it only a little.** At N = 8 nothing measurable (B3 +0.9 s, B2 and B1 slower; the spread of the repeats is 2 to 3 s). At N = 24
  B3 and B2 are 3.5 percent faster than B0 (7.5 s): the ranges of the three repeats do not overlap (213.5 to 218.8 against 220.8 to 226.2), so the gain is real but small.
  B2 equals B3 at N = 24 and is clearly worse at N = 8 (its fixed quota cannot give the 5070 Ti the candidates that the 1660S does not finish in time).
* **B1 (static waves) is the worst by far** (ClusterBenefit 0.66 at both N): every wave waits for the 1660S, 17 s against 4.5 s, so the 5070 Ti is idle most of the time. B3 is not weaker than B1: it is the
  stronger baseline, as MASTER says it must be kept.
* **Where the time goes.** About half of T is the update on the coordinator (44 s at N = 8, 111 to 122 s at N = 24), the same in every condition: no scheduling policy touches it. The candidates take
  40 s (N = 8) or 112 s (N = 24) on the 5070 Ti alone. The 1660S can take at most about one fifth of the candidates (its candidate is 3.8 times slower) and pays a 17.5 s synchronization
  per generation, so even a perfect scheduler could not give more than 10 to 15 percent of T. The real levers are the CPU noise (3.7 s of a 4.5 s candidate, and the same cost again inside the update) and the full
  synchronization; both are C4/engineering work, not C2.
* **The predictions.** N = 8: decision "eligible but not beneficial" (predicted CB 0.97); measured B3 1.011 (+1.1 percent): correct, the gain is far below the 5 percent bar. N = 24: decision "admitted"
  (predicted B3 203.2 s, CB 1.089, +8.2 percent); measured 216.3 s, CB 1.035 (+3.5 percent). **That is a false admission at the 5 percent threshold**: the 1660S does help, but by less than the bar.
  Errors of T: -5.0 to +8.3 percent at N = 8, -6.0 to +1.5 percent at N = 24 (G4, with a worse update estimate: 13 to 19 percent). The prediction of the order B0 ~ B3 < B2 at N = 8 and B1 worst
  (not predicted) was right.
  Analysis of the false decision at N = 24 B3: the candidate phase was predicted to be 18.1 s shorter than B0's and was 11.3 s shorter (100.9 against 112.2 s); the 1660S took 5 candidates per generation
  where 4 were predicted, but the 5070 Ti took 19 where 20 were predicted and the whole phase gained less; in addition the update was 3.7 s longer than B0's (114.7 against 111.0 s), which the model
  does not have (the same update on the same machine; contention for the coordinator's CPU or disk with the transfer of 1 GB to the 1660S is a hypothesis, not measured). The profile also over-estimates the 1660S
  synchronization (21.9 s in the profile, 17.5 s in the runs) in the other direction.
* **No policy changed the result.** Rewards and hashes are identical across the 24 runs, so the differences above are time only.

## What this does not show

Three repeats are three runs on one day, one pair of machines, one cable, one N pair, three generations (the first has no synchronization and publishes the initial weights): no confidence interval, and the
ranges are of three values. B0 vs B3 at N = 24 is a 3.5 percent difference with 3 runs each. The 1660S is both slower and has less CPU: with a better second GPU the picture changes. Nothing here says that the
cause of the long update is the CPU noise generation (it is the known cost, 4.3 s per candidate in isolation; the fixed part of about 10 s is not explained). The cross-GPU reward difference found in G4
(`../2026-10-07-g4-admission-b2/README.md`, 2 differing candidates in about 330 evaluations by the 1660S over G4 and G5) did **not** appear in these 24 runs: its rate is of the order of 1 percent or less, not established.
H0 (admission + sizing + sync policy as one system) was not run apart from B0/B3: sizing has nothing to size (both safe chunks are 1) and the synchronization is the full sync of G3 (the C4 replay is a later step).
