# G4: admission prediction against forced admission, and B2 (07/10/2026)

Runs of `scripts/run_benchmark.py` on the two machines over the direct cable (coordinator and the 5070 Ti worker on one machine, the 1660S worker
through SSH), summarized by `scripts/summarize_benchmark.py` (`summary-n8.*`, `summary-n24.*`). Every run: 3 generations, the same experiment id
`g4` (so every candidate has the same seed in every run), alpha 1e-3, sigma 1e-3. **One run per condition: no statistics.** The predictions are
`prediction-n8.json` / `prediction-n24.json`, copies of the files written from the v1 profiles before the first run (see `../2026-10-07-g4-profiles/`).

Conditions: **B0** the 5070 Ti alone; **B3** both workers, greedy dispatch (this is "forced admission" of the 1660S); **B2** both, quotas fixed in advance by
measured speed (largest remainder); **H0** the integrated system with the v1 profiles (admission decides, chunk 16 on the 5070 Ti).
T = mean time of one generation (candidates + update + publication). ClusterBenefit = T(B0) / T(condition); DeltaT = T(B0) - T(condition).

## Results (T in seconds)

| N | condition | T | wait for candidates | update | ClusterBenefit | DeltaT | predicted T | error |
|---|---|---|---|---|---|---|---|---|
| 8 | B0 | 85.0 | 38.9 | 45.5 | 1.000 | 0 | 86.3 | +1.5% |
| 8 | B3 (forced) | 82.8 | 36.4 | 45.6 | 1.027 | +2.2 | 89.0 | +7.5% |
| 8 | B2 | 92.6 | 47.1 | 44.7 | 0.918 | -7.6 | 106.1 | +14.6% |
| 8 | H0 (v1, chunk 16) | 80.4 | 34.8 | 44.9 | 1.058 | +4.7 | 81.5 | +1.4% |
| 24 | B0 | 228.6 | 112.0 | 116.0 | 1.000 | 0 | 257.7 | +12.7% |
| 24 | B3 (forced) | 211.6 | 97.9 | 113.0 | 1.081 | +17.1 | 239.6 | +13.2% |
| 24 | B2 | 215.2 | 96.9 | 117.7 | 1.062 | +13.4 | 256.2 | +19.1% |
| 24 | H0 (v1, chunk 16) | 206.5 | 99.1 | 106.7 | 1.107 | +22.1 | 243.4 | +17.8% |

Jobs of the 1660S (3 generations): N=8 B3 3 of 24, B2 6 of 24; N=24 B3 14 of 72, B2 15 of 72. It spends 35 s per run (3 syncs) fetching weights and is
idle 13 to 19 s while the others work; the 5070 Ti is idle 32 s in the N=24 runs with both workers (the last candidate of the 1660S is the tail).

## The admission decisions against what happened

* **N = 8: decision "eligible but not beneficial"** (predicted T 86.3 alone, 89.0 with the 1660S: 3 percent *worse*; a gain must exceed 5 percent). Forced
  admission measured **+2.6 percent (2.2 s)**: below the 5 percent threshold, so the decision "do not admit" stands, but the **sign was wrong**: the
  prediction said slower, the run was slightly faster. One run: 2.2 s is inside what the same machine varies by between runs (not measured here).
* **N = 24: decision "admitted"** (predicted 257.7 -> 239.6, +7.0 percent). Measured **+7.5 percent (17.1 s)**. Direction and size right.
* **No false decision at the 5 percent threshold in these two cases.** The absolute times are over-predicted by 13 to 19 percent: the update cost in the v1 profile
  (6.18 s per candidate, the median of three noisy samples) was higher than in the runs (5.7 at N=8, 4.8 at N=24). B2 was predicted worse than B3 and was.
* What the 1660S buys: at N = 24 it adds about 8 percent; at N = 8 nothing measurable. The reasons are in the table: the update (about half of T) runs only on
  the coordinator, a generation starts with a 22 to 35 s synchronization for the 1660S, and one candidate there takes 17 s against 4.5 s.

## What went wrong, and what it shows

1. **The weak safe-chunk probe.** H0 used chunk 16 on the 5070 Ti because the v1 profile (2 perturbed candidates) found it exact. In the N=24 run the rewards of generation 0
   differ from B0 at candidate 21 (0.1875 against 0.25), so H0's weights hash differs from B0's: chunk 16 is **not** equal to chunk 1 on the same GPU. The v2 profile
   (32 candidates) rejects every chunk above 1 on both GPUs. The H0 rows above are therefore "chunk 16, unsafe", kept as evidence; they are not a result for H0.
   With the v2 profiles H0 is the same configuration as B0 (the 5070 Ti alone, chunk 1) and the two should be reported as one (MASTER section 9).
2. **A 1660S evaluation can differ from a 5070 Ti evaluation at chunk 1.** The N=24 B2 run diverges from B0 in generation 1: candidate 2, evaluated by the 1660S, scored
   0.3125 against 0.25 (the parent weights were identical). The single-process reference, run on each machine alone with the same seeds
   (`references/`), confirms that it is the hardware and not the distributed code: **generation 0, candidate 21: 5070 Ti 0.25, 1660S 0.1875**, all other 23 rewards equal.
   So the claim of G3 ("every reward bit-identical across the two machines") held for 24 candidates and does not hold in general: a candidate can differ by one
   question (0.0625): 1 of 24 in the reference, and none in 264 evaluations by the 1660S in the later G5 runs (`../2026-10-07-g5-benchmark/`), so the rate is small and not established. It matters for the claims: a result depends on which GPU evaluated which candidate, and B3 assigns by timing, so two B3 runs of the same experiment
   can end with different weights. B3 and B0 gave identical hashes at N=24 and N=8 only because the 1660S did not evaluate a differing candidate in those runs.
   The check "identical rewards and hashes" of `summarize_benchmark.py` fails at N=24 for this reason (3 distinct outcomes: B0 = B3, B2, H0); the N=8 runs all agree.

## What this does not show

One run per condition, no variance; two values of N; the predictions come from one set of measurements and one run order; the 1660S profile and the benchmark share
a machine and a cable, not tested apart; the cause of the cross-GPU difference (different kernels in FP16 attention or matmul on sm_75 and sm_120) is not isolated;
how often it happens is known only as 1 candidate in 24 (generation 0 of the references), 1 in about 10 comparable evaluations of the B2 run and none in the 264 of G5.
