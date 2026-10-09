# Several candidates at the same time on one GPU (09/10/2026)

Written by the AI, **not reviewed by the owner**. Question (the owner's): a GPU with spare VRAM could run 2 or 3 candidates at once; does that raise throughput? `run_probe.sh` starts K copies of `scripts/chunk_text_record.py` at the same moment on ONE GPU (each copy: the parent + 4 perturbed candidates of `cot_l1_q128`, CUDA noise engine, FP32, chunk 64, seconds per condition); `summarize_probe.py` makes the table. Gain = K x t(1) / t(K): 1.00 = no gain, K = perfect.

## Results (`3060-first/summary.txt`, `5070ti/summary.txt`)
| GPU | K | seconds per candidate | gain | same texts as K = 1 |
|---|---|---|---|---|
| RTX 5070 Ti | 1 | 6.26 | 1.00 | yes |
| | 2 | 12.88 | 0.97 | yes |
| | 3 | 19.20 | 0.98 | yes |
| RTX 3060 (first) | 1 | 16.09 | 1.00 | yes |
| | 2 | 42.63 | 0.75 | yes |
| | 3 | 56.72 | 0.85 | yes |

**At chunk 64 more processes on one GPU give no gain** (5070 Ti: the time grows in proportion to K; 3060: slower than one after the other). The answers are the same text, so it is only a speed question. This is a direct measurement of what the owner's question asked, and it is the evidence that the GPU is already fully used at chunk 64 (the earlier statement that it is "saturated" was an inference).

## What this does NOT show
* Only chunk 64 and the workload `cot_l1_q128`. The G7 benchmark (`STATUS`, other workload, CPU-side noise) found a gain of about 18 percent with 2 processes at chunk 16: smaller chunks with several processes were NOT measured here and could behave differently (but they would have to beat chunk 64 with one process to matter).
* The K processes start together but load the model at slightly different moments; 5 conditions per process (the parent is left out of the median), one run per K: no interval.
* The 1660S (6 GB, no room for several processes) and the second 3060 were not measured.
* Not the end-to-end effect on a generation (the old plan `B0x2` benchmark, stopped after about 12 minutes: `../2026-10-09-concurrency-5070ti-ABORTED-restart-later/`, no usable result).
