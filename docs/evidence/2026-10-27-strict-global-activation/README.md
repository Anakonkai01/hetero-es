# Removing activation shared staging: rejected prototypes

Hardware counters motivate a dataflow change: keep the existing MMA tile and streamed FP16 weights,
load activations through global/L1, and use the freed shared memory to admit more CTAs. This retains
B22 quantization, exact integer sums and final rounding. Two implementations are measured separately.

- `global_input.py` reads the existing row-major packed planes directly. Three tests compare both column
  sizes and splits 1/3/7 at K=64/80/1040, row/column tails, against the independent CPU integer oracle;
  **3 pass**. The extra scalar loads are expensive: a decode gate example rises from approximately
  **26.3 to 45.8 µs** even with four resident CTAs.
- `native_input.py` first packs each m16/k32 tile into the tensor instruction's native register fragments,
  allowing one coalesced uint4 load per digit. **3 tests pass** against the same CPU oracle. The pack launch
  and scratch are explicit. Benchmarks report both packing plus projection and projection alone, without
  pretending that packing is free. Gate core time is essentially unchanged (**26.30 versus 26.27 µs**);
  down core time is also unchanged (**14.02 µs**), while cold controls regress. Prefill does not improve
  either. No fused producer publishing the new layout was implemented after this operator gate failed.

The new layout raises decode residency from three to four CTAs in the measured builds, yet that does not
translate into speed. This is evidence against these implementations, not evidence that occupancy alone
determines performance. It also identifies what a later design would need to preserve: coalescing and
operand prefetch, alongside a bounded scratch and unchanged producer/consumer semantics.

`bench.py` captures external CUDA timing events around each operation. Cold tests evict 128 MiB outside
the timed interval, rather than subtracting independent flush timings. Warm/cold absolute durations include
the captured event schedule; comparisons use the same schedule and repeated baseline controls. They are
not substituted for the project's end-to-end request timings.

## What this does NOT show

No whole-model gain, cross-GPU/native, failure-lifecycle, package or managed acceptance is established.
The transposed producer is a standalone scratch conversion, not an integrated runtime feature. No second
full inference model or persistent weight shadow is created, and no runtime source/default is changed.
