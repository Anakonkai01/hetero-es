# C1 again: the admission prediction against forced admission, on the CUDA engine and a long workload (08/10/2026)

Written by the AI, **not reviewed by the owner**. Repeats `../2026-10-07-g4-admission-b2/` (EQ2A) with the profile of `scripts/profile_worker.py` after it learned to profile any workload and either noise engine.

## What was done
* Workload `cot_l1_q128` (128 questions, level 1), CUDA noise engine, FP32 evaluation, N = 24 candidates, 3 generations per run, alpha and sigma 1e-3, experiment id `c1v2`, both workers at chunk 64, coordinator noise threads 28.
* Profiles: `profile-5070ti-l1q128-cuda.json` (chunks 1, 16, 64; 8 perturbed probe candidates; 3 timed candidates; update cost) and `profile-1660s-l1q128-cuda.json` (chunks 1, 64; 8 probe candidates; 3 timed candidates; update cost; synchronization over the cable). Both: safe chunk 64, all probes identical to chunk 1 (the check against a recorded answer exists only for the 16 prompts, so for this workload it is "chunk 1 twice gives the same text", `reference_kind`).
* `prediction-n24.json` was written by `scripts/predict_admission.py` from the two profiles BEFORE any benchmark run.
* `bench-n24/`: B0 (5070 Ti alone), B3 (both, greedy: forced admission of the 1660S), B2 (both, quotas by measured speed), 2 repeats each, run round-robin by `scripts/run_benchmark.py`. `summary-n24.txt` is `scripts/summarize_benchmark.py` on them.

## Result (T = seconds per generation without generation 0; CB = T(B0) / T(condition); ± = 95 percent interval over the 2 repeats)
| condition | predicted T | measured T | predicted CB | measured CB | jobs of the 1660S (of 72) | candidate seconds, 5070 Ti / 1660S |
|---|---|---|---|---|---|---|
| B0 | 194.9 | 151.5 ± 2.1 | 1.000 | 1.000 | - | 6.9 / - |
| B3 (forced) | 188.7 | 135.1 ± 1.3 | 1.033 | **1.122 ± 0.019** | 14 | 7.0 / 28.1 |
| B2 | 162.8 | 128.7 ± 4.7 | 1.197 | 1.178 ± 0.046 | 12 | 7.0 / 28.9 |

* **The decision for B3 was wrong.** The prediction said ELIGIBLE_BUT_NOT_BENEFICIAL (a gain of 3.3 percent, under the 5 percent threshold, so "do not admit"); forced admission measured +12.2 percent. A false decision, published here as the rule says (MASTER section 8). The prediction for B2 (+19.7) is close to the measurement (+17.8), and the ordering B2 > B3 > B0 was right.
* **Absolute times are over-predicted by 26 to 40 percent.** The cause that can be seen: the profiles' candidate times are higher than the candidates took in the runs (5070 Ti 8.02 s in the profile, 6.9 to 7.0 s in the runs, +16 percent; 1660S 35.25 s against 28.1 to 29.0 s, +22 percent). Why the profile overestimates is NOT isolated here. (Not the cause for the 1660S: nothing else ran on it. For the 5070 Ti the test suite did run on the same GPU during its profile, so that figure may also contain interference; this was a mistake of the AI, not a designed condition.)
* **Post hoc, labelled as such:** with the candidate times measured in these runs (6.95 s and 28.4 s) in place of the profile's, the same program predicts ADMITTED with +9.6 percent for B3 (`posthoc-prediction-n24-with-measured-candidate-times.json`). So the wrong decision comes from the profile's candidate times, mostly from the 1660S's being over-estimated more than the 5070 Ti's. That is an explanation fitted after seeing the data, not a tested claim.
* **Same weights everywhere:** all 6 runs end with the same rewards and the same weight hash (`identical_rewards_and_hashes: true`), although the 1660S evaluated 14 (B3) or 12 (B2) of 72 candidates: at chunk 64, FP32, CUDA engine, the two GPUs agree on this workload.
* The column `pred` of `summary-n24.txt` is empty on purpose: `summarize_benchmark.py` reads the prediction variant for a common chunk 1, which is not what ran here; the table above uses the variant `per_worker_chunk` of `prediction-n24.json`.

## What went wrong on the way (kept for the review)
1. First profile of the 1660S (`profile-attempt1-failed.log`): after about 3 hours of measurement the synchronization step failed because the weights server listened on port 8766 and only 8765 is open between the machines; nothing had been written. `profile_worker.py` now checks the server first and saves `.partial` results.
2. Second attempt (`profile-attempt2-light-aborted.log`): the AI had lowered the rigor to save time (3 probe candidates, chunks 1 and 64, 2 timed candidates) without asking; stopped after about 17 minutes and run again at full rigor. The final 1660S profile did not measure chunk 16 (the 5070 Ti's did); the chunk used is 64.
3. The AI also ran the test suite on the 5070 Ti while its profile ran (see above).

## What this does NOT show
Two repeats per condition (the intervals come from two values); one pair of GPUs; one N (24); the profile's candidate times were the weak input (not explained); no test of the decision at the threshold of 5 percent from the other side (a case where the prediction is "admit" and the run loses); B3 here has one process per GPU, unlike the best configuration of G7 (two processes on the fast GPU); the 1660S profile and the benchmark share a machine and a cable.
