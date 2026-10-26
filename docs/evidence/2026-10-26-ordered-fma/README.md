# Rejected ordered FP32 FMA projection pilot

Selected runtime remains B22 `b1ef257a`; repository HEAD at measurement is `4d488217`. The scratch
prototype reads live FP16 weights directly and uses explicitly rounded FP32 FMA in fixed 256-term
chunks, retaining subnormals inside each chunk. Chunk outputs are flushed to signed zero, then
merged in a fixed pruned adjacent-pair FP32 add/FTZ tree. Bias uses the same add rule. The arithmetic
identity is separate from B22 and does not vary with batch size or GPU architecture. No transformed
weight cache or second GPU model is used; FP32 partial scratch is bounded to 16 MiB.

The independent CPU Fraction oracle rounds exact multiply-plus-add once to IEEE binary32. Three
tests pass on the local 5070 Ti: fused-rounding and internal-subnormal counterexamples, signed-zero
and ragged/offset cases, and live FP16 weight changes/restore. The final GPU receipt is
`gpu-5070ti-02.log`; the earlier receipt precedes initialization of unused last-loop operand slots.

One finite five-shape operator pilot compares with selected B22. Each CUDA graph replay contains
thirty calls; ABBA ordering yields ten event-time samples per variant. Every case shares a single
FP16 weight tensor, and outputs are sampled against each arithmetic's independent CPU oracle.

| Shape (M,K,N) | B22 median µs | Ordered FMA median µs | B22/FMA speed ratio |
| --- | ---: | ---: | ---: |
| 32,896,128 | 5.946 | 21.577 | 0.276 |
| 32,896,896 | 10.634 | 21.703 | 0.490 |
| 32,896,4864 | 28.137 | 42.284 | 0.665 |
| 32,4864,896 | 36.082 | 42.938 | 0.840 |
| 32,2048,5632 | 65.188 | 99.186 | 0.657 |

The implementation is slower in every measured case. Stop this branch; do not extend it to a full
decoder or spend native/candidate qualification on this implementation. This rejects this specific
shared-memory SIMT design, not every possible fixed-order floating-point implementation.

Final source, CPU oracle, tests and benchmark are in `harness/`. Run with
`PYTHONPATH=runtime/src:<this-folder>/harness` and the isolated heteroes-match Python;
GPU tests require `HETEROES_GPU_ACCEPTANCE=1`, and the benchmark additionally requires `--gpu`.
Raw times and build identities are in `operators-5070ti-01.json`.

## What this does NOT show

Selected runtime changes, whole-model speed, cross-GPU or native Windows acceptance, complete
nonfinite/resource/stream/lifecycle qualification, broad quality, learning, or near-vLLM performance.
No push, merge or deployment occurred.
