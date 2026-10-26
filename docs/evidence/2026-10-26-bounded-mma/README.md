# Unselected bounded floating-point MMA experiments

Selected runtime remains `b1ef257a` (B22 prefetch); repository HEAD when these experiments concluded
is `4d488217`. No runtime file changes are selected from this folder.

The experiment changes projection arithmetic under a separate probe identity: quantize activations
and live FP16 weights into small signed integers, compute bounded FP16-input/FP32-accumulator MMA
partials, then convert each exact integer partial to int64 and merge through the integer encoder.
For activation/weight magnitude bits A/W, at most `2**(24-A-W)` products enter one FP32 partial.
Every possible intermediate integer magnitude is at most `2**24`, so single-precision accumulation
is exact regardless of the allowed accumulation order. This preserves this new quantized arithmetic,
not historical B22 outputs. The original FP16 weight set remains primary; no full transformed model
is retained. The independent CPU oracle uses rational quantization and integer products.

The own-kernel pilot tests A8/W8, A10/W8 and A11/W6. The half2 variant accelerates weight quantization
with explicitly rounded half2 multiply/add/subtract, checked against every admitted finite FP16 bit
pattern across forty row exponents. The vendor variant uses `torch.bmm` with FP16 inputs/FP32 output,
requires full-precision accumulation flags, bounds quantized-weight scratch to 32 MiB and partial
scratch to 16 MiB, and falls back to its own same-arithmetic implementation outside the supported
shape range. It is a separate experiment, not a vendor-free strict runtime result.

Seven bounded-arithmetic tests pass on each of SM120 and SM86; five half2 tests pass on each.
Two vendor tests pass on SM120, including live weight changes/restore, scratch clearing and
precision/stream guards. A cancellation counterexample detects an unsafe doubled FP32 partial
length; that GPU mutant and a wrong CPU tie-parity mutant are both killed. Initial failed build,
instruction-audit and red-test attempts are retained. The included decoder test was red before its
helper was written; the decoder helper was never green-tested or timed and is not accepted.

Operator timings use thirty calls in one CUDA graph replay and interleaved forward/reverse variant
order, ten samples each. Both variants share each case's one FP16 weight tensor. Ratios below are
baseline B22 median latency divided by prototype latency; above one is faster.

| Pilot | GPU | Cases | Minimum ratio | Maximum ratio |
| --- | --- | ---: | ---: | ---: |
| Own A8/W8 | 5070 Ti | 14 | 0.677 | 1.107 |
| Own A10/W8 | 5070 Ti | 14 | 0.673 | 1.131 |
| Own A8/W8 | 3060 | 14 | 0.814 | 3.100 |
| Own A10/W8 | 3060 | 14 | 0.707 | 4.185 |
| Half2 A8/W8 | 5070 Ti | 14 | 0.659 | 1.246 |
| Half2 A8/W8 | 3060 | 14 | 0.236 | 1.537 |
| Vendor A8/W8 | 5070 Ti | 5 | 0.948 | 1.315 |

The five vendor ratios in shape order `(M,K,N)` are `(32,896,128)` 0.948,
`(32,896,896)` 1.148, `(32,896,4864)` 1.290, `(32,4864,896)` 1.315 and
`(32,2048,5632)` 0.957. Faster individual cases do not establish an end-to-end gain. Local gains
are inconsistent, and arithmetic/quality changes would add substantial qualification work. Stop
these implementations here; retain them as research evidence rather than extending local tuning.

Final harness sources are in `harness/`; operator JSON retains build identities and raw event times.
Use `PYTHONPATH=runtime/src:<this-folder>/harness` with the isolated heteroes-match environment,
`HETEROES_GPU_ACCEPTANCE=1` and `--gpu` for benchmarks. `bounded_reference.py` also imports the
selected runtime's integer encoder. Remote tests used the approved standalone 3060 WSL2 environment
and process-local CUDA driver search path; device contribution state was not changed.

## What this does NOT show

Selected runtime changes, full-model speed, quality or learning acceptance, native Windows acceptance,
universal floating-point MMA portability, arbitrary heterogeneous candidate parity, managed ownership,
or near-vLLM performance. No full-weight ES on a quantized primary model was substituted for the
approved FP16-first plan. No push, merge or deployment occurred.
