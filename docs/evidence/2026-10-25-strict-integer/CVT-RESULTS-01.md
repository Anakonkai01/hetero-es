# Unselected exact-conversion prototype

Selected product source remains `fb18a7b7`. The distinct scratch variant is stored as `source-cvt-prototype-01.py`
with `source-cvt-audit-01.py`. It replaces integer shifts/tie branches for **weight** quantization with an exact
power-of-two exponent-bit adjustment after exact FP16 widening, then PTX `cvt.rni.s32.f32`. It does not change the
reference's quantization law, use a floating multiply or replace the integer dot with floating Tensor Cores.

For admitted finite nonzero FP16 weights, row exponents span [-24,15]. The scaled value is always a normal FP32:
at least 2^-26 for B14 or 2^-18 for B22, and less than 2^B. Exponent adjustment therefore has no rounding, underflow
or overflow; the integer conversion exactly implements ties-even RNE within int32 range. Zero/nonfinite branches
remain explicit; the row metadata/error pass rejects nonfinite weights before generation.
[PTX integer rounding](https://docs.nvidia.com/cuda/parallel-thread-execution/index.html#integer-rounding-modifiers)
defines `.rni` as nearest integer with even ties. This domain argument is essential to permitting the conversion in
the integer-module audit; it is not a license for arbitrary FP32 scaling or a floating dot.

`quant-{baseline,cvt}-nhut-03.json` and `quant-{baseline,cvt}-thao-01.json` each check all **1,017,852 admitted finite
FP16 value/row-exponent pairs per precision**. Both B14 and B22 match the independent exact-power-of-two FP64 rounding
oracle. `cvt-{nhut-03,thao-01}.log` records 99 passing reference/operator/decoder tests per prototype target before
running same-host baseline/variant synthetic sweeps. The first two Nhut receipts are retained harness failures,
not numerical counterexamples. The corrected harness is `probe-half-quant-03.py`.

`cvt-comparison-01.json` compares sequential synthetic operator event measurements on Nhut's 5070 Ti. Whole-call
timing includes input quantization and a weight-row metadata refresh on every call. B1 SIMT improves roughly
1.2–1.6x; B32 improvement depends on shape/geometry and is smaller. No GPU isolation or serving latency is claimed.
Thao's complete baseline/variant sweeps are also retained as `split-{baseline,cvt}-thao-01.json`.

The local trained scratch results below use the same controlled workload as the selected baseline: eight tokenized
prompts, 32 output tokens, context 512, warmup excluded, median of three synchronized host wall measurements.

| Model / local 5070 Ti | B22 B1 | B22 B8 | B22 B32 |
| --- | ---: | ---: | ---: |
| SmolLM2-360M | 249.4 | 497.9 | 1451.6 |
| TinyLlama-1.1B | 174.4 | 344.7 | 918.9 |
| Qwen2.5-0.5B | 254.7 | 531.3 | 1507.7 |

`bench-cvt-*-b22-nhan-01.json` retains repeat/single-row token checks. `quality-cvt-*-nhan-01.json` repeats parent,
canonical seed 7001 at ±sigma 1e-3, and restored parent with FP32, B14 and B22 engines sharing the live FP16 model.
`cvt-trained-comparison-01.json` asserts consumed files/workload/weight equality and equality of prefill hashes,
tokens, text and rewards with the baseline on every measured state. Exact weight restore and restored inference
also pass. This includes preserving the baseline B14-vs-FP32 Qwen counterexample.

## What this does NOT show

This variant is **not selected or qualified**. Trained measurements here are local; the prototype's 3060 runs check
operators/small graph composition, not these trained models. Native Windows, four-target source acceptance,
production GPU role ownership, general accuracy and the full M0–M6 objective remain open. Performance still falls
far short of vLLM at B32. No previous receipt or selected-source result was replaced by this variant.
