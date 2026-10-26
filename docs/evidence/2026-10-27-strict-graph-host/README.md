# Bounded host work in strict generation

Selected source: `5c2f849c`, against `267ba0b5`. Clear FP32 KV slabs in one foreach operation, construct
completion publication as one padded CPU list plus one device copy, and retain one strict penalty inverse
keyed by its FP32 identity. The reciprocal still runs the original strict sequence; failures do not replace
a valid cached constant. No numerical recipe or model weights are changed.

Two new CPU tests cover FP32-equivalent input values, bounded replacement and error handling. **44 targeted
GPU tests** pass in `raw/gpu-5070ti-01.log`. ABAB Qwen B32 full-generation controls have equal token hashes;
the mean of two round medians improves short32 by **1.96%** and chat128 by **0.51%**. Full combined-source
platform checks are tracked separately in `2026-10-27-strict-combined-acceptance`.

## What this does NOT show

This directory alone does not qualify later changes, native Windows, managed worker/package lifecycle,
quality or learning behavior, or the 80% vLLM target. All raw timing and test scopes remain explicit.
