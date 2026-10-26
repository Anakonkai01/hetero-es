# B22 hardware-counter attribution, 2026-10-27

These are synthetic matching-shape kernels from frozen `0eb86cb9`, not complete request timings. NVIDIA
Nsight Compute **2026.1.1.2** is extracted only into private scratch from the official redistribution;
the archive SHA-256 matches NVIDIA's [CUDA 13.2.1 manifest](https://developer.download.nvidia.com/compute/cuda/redist/redistrib_13.2.1.json).
The [archived requirements](https://developer.nvidia.com/tools-overview/nsight-compute/get-started-2026_1)
cover this profiler/driver combination. No driver, existing environment, deployed process or clock lock is
installed or changed. CLI build/version, source/binary hashes and generated reports are retained.

The driver restricts counters to administrators. Profiling uses the owner's already supplied sudo authority;
the restriction itself is not changed. The first noninteractive sudo attempt failed before profiling and
is retained. Subsequent authenticated profiling succeeds. Authentication input is not stored in evidence.

Each program warms the source first, marks one operation with `cuProfilerStart/Stop`, and collects the full
counter set with `--clock-control none --cache-control all`. The profiler therefore warns about unlocked
frequencies. Frequencies range from 2.63–2.85 GHz across these runs; compare counters, not absolute
profiled times as if they were the matched end-to-end benchmark. Cache flushing/replay also differs from
the full decoder's naturally evolving cache state.

| Kernel / shape | Profiled µs | DRAM throughput | SM throughput | Theoretical active warps/SM |
| --- | ---: | ---: | ---: | ---: |
| Prefill gate: M888/K896/N4864 | 250.78 | 6.19% | 70.60% | 12 |
| Prefill down: M888/K4864/N896 | 252.99 | 9.73% | 69.82% | 12 |
| Decode gate/up: M32/K896/N9728, S2 | 27.10 | 73.56% | 45.95% | 12 |
| Decode down: M32/K4864/N896, S7 | 14.56 | 71.77% | 42.93% | 12 |
| Bounded head scores: M32/K896/V151936 | 204.45 | 77.54% | 68.55% | 16 |
| GQA decode attention, actual short-length range | 10.72 | 19.22% | 29.69% | 14 |

Percentages are Nsight's throughput metrics, not OS GPU utilization. Prefill is predominantly tensor/issue
limited in these shapes. The cold decode shapes are more bandwidth constrained; the blanket inference
that every decode projection is already at roughly 80% tensor peak is too strong. Attention spends much
of its time on fixed-latency dependencies. This directs new experiments toward data movement and internal
parallelism rather than precision changes.

Prefill reports include 32-byte local frames and local spills. The SASS export shows those stores/loads at
entry and epilogue, not repeated every K step; the profiler's automated speedup estimates are suggestions,
not measured gains. Subsequent [global-activation](../2026-10-27-strict-global-activation/README.md) and
[wide-attention](../2026-10-27-strict-wide-attention/README.md) probes test two dataflow hypotheses and are
rejected by their actual timings.

The initial profiler helper's unused head branch had an incorrect `prepare` signature. V2 fixes that
before running the head case; the measured initial prefill source and its receipt remain unchanged.

## What this does NOT show

These isolated counters do not prove a full-model bottleneck, a theoretical B22 ceiling, an end-to-end
speedup, other-device/native qualification or the 80% objective. Synthetic shapes are not trained model
or learning evidence. Profiler suggestions and unlocked-clock durations are not substituted for ABAB
request results. The runtime remains unchanged.
