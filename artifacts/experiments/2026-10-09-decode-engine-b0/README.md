# The compacting decoder as a recipe option, in the real system (09/10/2026)

Written by the AI, **not reviewed by the owner**. `run.sh` runs `scripts/run_benchmark.py` (condition B0: the 5070 Ti alone, coordinator + worker processes, HTTP, ledger) with `--decode-engine hf_compact` (2 runs) and with
`--decode-engine hf_generate` (1 run, same session): N = 24 candidates, 3 generations, workload `cot_l1_q128`, CUDA noise engine, FP32, chunk 64, experiment id `c1v2` (the same as `../2026-10-09-three-machines/`).
`summary-compact.json` and `summary-generate.json` are made by `scripts/summarize_benchmark.py`. The decoder is `src/heteroes/eval/compact_decode.py`, reached through the recipe field `decode_engine`.

## Results
| decode engine | runs | T of a generation (steady state) | final weights |
|---|---|---|---|
| `hf_generate` (default) | 1 | 150.8 s | `a02a640b…` |
| `hf_compact` | 2 | 94.4 +- 0.1 s | `a02a640b…` (both runs) |

* **1.60 times faster per generation**, in the real system, not only in a decoding probe (the rollout is the main cost of a candidate; the coordinator's update and the other fixed costs are the same in both).
* **The final weights are the same hash** as every earlier B0 run of this experiment id (`../2026-10-09-three-machines`, `../2026-10-09-dispatch-3060`): all 24 candidates of the 3 generations got the same rewards with both engines (`identical_rewards_and_hashes: true` inside each summary; the hash equality between the two folders was read from the two summaries). The recipe hashes of the two engines differ, as designed.
* The earlier B0 runs of the day (`hf_generate`, two runs of `../2026-10-09-three-machines`) gave 151.6 +- 5.0 s; the run here gave 150.8 s.

## What this does NOT show
* One GPU (the 5070 Ti) and one workload; the cluster effect of a faster 5070 Ti (it changes the speed ratio to the other machines, so the share of candidates and the cluster benefit change) was NOT measured. The 3060 and the 1660S were not used.
* Equal rewards in 3 generations x 24 candidates is a sample of 72 evaluations: it does not exclude a rare tie that flips a text (`docs/numerical-contract.md` section 17).
* One run with `hf_generate`.
