# Chunk 128 for the workload `cot_l1_q128` (09/10/2026)

Written by the AI, **not reviewed by the owner**. Question (TODO group `chunk-128`): can the 128 questions of `cot_l1_q128` be answered in ONE `generate()` call (chunk 128) on every GPU, giving the same text as chunk 1, and is it faster than chunk 64?

## What was run
* `probe-5070ti.json`, `probe-3060.json`: `scripts/profile_worker.py --workload cot_l1_q128 --noise-engine cuda --chunks 1,64,128 --probe-candidates 8 --candidates 1`. The parent weights and 8 perturbed candidates (seeds 7001 to 7008) are answered at chunks 1, 64 and 128; "identical" means the same TEXT as chunk 1.
* `texts-5070ti.json`, `texts-3060.json`, `texts-3060b.json`: `scripts/chunk_text_record.py run --chunk 128 --candidates 8` (new script): the text (and its sha256) of every answer at chunk 128, for the parent and the same 8 candidates. `texts-comparison.json` is `compare` over the three files. (`texts-3060b` is the SECOND borrowed 3060, in another city.)
* `speed-5070ti-64-vs-128.json` (chunks 1,64,128, 1 probe candidate, 5 real candidates at the safe chunk 128) and `speed-5070ti-chunk64.json` (chunks 1,64, 5 real candidates at chunk 64). `*.log` are the logs; `speed-5070ti-chunk64.log.killed-by-power-cut` is a first attempt that the breaker of the owner's socket stopped.
* `cudaengine-3060b.json`: `cuda_engine_crossgpu.py` on the second 3060.

## Results
| GPU | chunk 128 same text as chunk 1 (parent + 8 candidates) | peak memory at chunk 128 |
|---|---|---|
| RTX 5070 Ti | yes | 4.5 GB |
| RTX 3060 (first) | yes | 4.5 GB |
| RTX 3060 (second, other city) | not run by `profile_worker` (see below); its chunk-128 texts equal those of the other two | not measured |

* **Same text across GPUs:** 1152 answers per pair (9 conditions x 128 questions), 5070 Ti against each of the two 3060s: 0 differ (`texts-comparison.json`, `all_equal: true`).
* **The CUDA noise engine on the second 3060** gives the same 10 hash fields as the 5070 Ti and the first 3060 (`compare_cudaengine.py`, output in `cudaengine-comparison.txt`).
* **Speed on the 5070 Ti: no clear gain.** One evaluation of the 128 questions, mean over 2 conditions: 6.62 s at chunk 64, 7.22 s at chunk 128. A whole real candidate (perturb + rollout + restore), 5 samples: chunk 64 median 8.01 s (range 6.84 to 8.23), chunk 128 median 7.44 s (7.44 to 7.45). The two ways of measuring disagree in sign; the differences are within about 10 percent. On the first 3060 one probe gave 15.8 s at chunk 128 against 17.0 s at chunk 64 (about 7 percent, one sample). **The AI's earlier guess of 1.2 to 1.7 times faster is refuted for the 5070 Ti.**
* **On the 6 GB GTX 1660 SUPER chunk 128 is at the limit:** the allocator reported out-of-memory warnings (free 5 to 75 MB) and recovered each time by freeing its cache (`texts-1660s.log` was NOT copied: the machine went down; the warning lines are quoted from the first minutes of that run).

## What this does NOT show
* **Nothing about the GTX 1660 SUPER:** it went down twice (the breaker of the socket) while its probe and its text record were running; no result from it. The criterion "same text on every GPU" is met on three runs of two GPU models (both 3060s are the same model), not on the weakest card.
* Equality of text at chunk 128 is measured, not guaranteed: nothing in the cuBLAS or PyTorch documentation promises it for other batch sizes or other GPU architectures. The 4060 (Ada) and any new GPU model need their own probe.
* The speed numbers are one machine and small samples; the 5-sample medians of chunk 64 have a wide spread. No claim about a gain in a full run (the B0 against T2 run at chunk 128 was NOT done, because chunk 128 gave no clear speed-up).
* A different chunk per worker (so that each GPU uses its VRAM) was not built: with no clear gain it is not justified now.
* The second 3060 got the test suite (2071 passed, 20 skipped, `tests-3060b.log`) and the text record, but no `profile_worker` probe or speed measurement of its own.

## Pitfalls met (all fixed or noted)
* The AI passed the model path of the 5070 Ti to the 1660S (first launch failed at once; relaunched).
* `chunk_text_record.py` had a bug in its last line (`environment_info()` needs the device): a whole run was lost on each machine; fixed, rerun.
* The second 3060: someone ran `apt install nvitop` at 11:59 (the Ubuntu NVIDIA 580 libraries shadow the Windows driver: CUDA segfault; worked around with `LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811`, the package was NOT removed); and it had no C compiler: the AI installed `gcc`, `libc6-dev` and `python3.14-dev` with the owner's sudo password (needed by Triton).
