# Where the time of the compacting decoder goes (09/10/2026)

Written by the AI, **not reviewed by the owner**. `profile_decode.py`: torch.profiler over ONE call of the compacting decoder (`../2026-10-09-compact-decode/compact_general.py`) for 64 questions of the project's arithmetic workload (parent weights, FP32, Qwen2.5-0.5B, RTX 5070 Ti, 256 steps, 6,311 slot-steps, 20 compactions). `profile-5070ti-chunk64.txt` is the output; `profile-5070ti-chunk64.FIRST-RUN-wrong-totals.txt` is a first run of the same thing whose two summary lines double-counted (the script added operator rows to the kernel rows: 3.62 s and 616,228 launches); the tables in both files are the same kind of data, the summary lines of the second are right.

## Measured
* Wall time without the profiler: 2.236 s (8.7 ms per decoding step). Under the profiler 3.575 s (the profiler slows the CPU side).
* GPU kernel time: 1.809 s (7.1 ms per step) = about 81 percent of the unprofiled wall time. The rest (about 19 percent) is the GPU waiting for the CPU.
* 1,248 kernel launches per decoding step (319,497 in 256 steps).
* Share of the GPU kernel time (from the table): matrix products `aten::mm` 59.6 percent, `addmm` 10.2 percent, `bmm` 4.6 percent: **74 percent in matrix products**, almost all by the plain FP32 kernels of CUDA cores (`cutlass_80_simt_sgemm_*`, `gemmSN_TN`, gemv: no tensor cores); the remaining 26 percent is small element-wise operations (`mul` 7.0, `copy_` 6.3, other element-wise 12, `cat` of the key/value cache 3.0, `add` 2.2).
* CPU side (self time, under the profiler): `cudaLaunchKernel` 19.5 percent, `cudaStreamSynchronize` 8.9 percent (the host reads `finished.all()` and `finished.any()` at every step), then the operators.

## What it suggests (inference, nothing was tried)
* The step is mainly GPU-bound (81 percent busy) with a launch-bound tail of about 19 percent. CUDA graphs would remove part of the 19 percent with the SAME kernels (so no change of bits is expected), but the batch shape changes at every compaction, so a graph per batch size would be needed.
* A step moves the 2 GB of FP32 weights through the matrix kernels (2.2 ms at the 5070 Ti's memory bandwidth, a floor of about a third of the 7.1 ms): FP16 weights in memory widened inside the kernel would halve that, but needs a custom kernel and changes the order of the sums (bits).
* Fusing the element-wise operators (26 percent) with `torch.compile` could save part of it, at the risk of different rounding.
* TF32 or FP16 tensor cores would be far faster but are excluded by the numerical contract (O8) and by the Turing card (no TF32).

## What this does NOT show
* One GPU, one model, one batch of 64 questions with short answers (the arithmetic workload: mean answer about 25 tokens in this first batch, so the batch is small for most steps), the parent weights only. A task with long answers (GSM8K) has a larger average batch and a different split between weight-reading and compute.
* The percentages are those of a profiler run (which inflates the CPU side); the kernel times themselves are not inflated much.
