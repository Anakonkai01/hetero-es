# strict_b22_v1 as a Recipe v3 decoder (M1 executor integration), 2026-10-27

Decision: [ADR-013](../../../runtime/docs/adr/ADR-013-strict-b22-recipe-decoder.md). Code: `eval/strict_backend.py`,
`catalog.STRICT_B22_DECODER`, `v3/options.exact_chunks`, document/option validation, `study/evaluation.generate_rows`
routing, `executor.py` failure mapping and load-time graph check, `product/v3.strict_options`.

- A new value `strict_b22_v1` of `evaluation.decoder`; it requires `evalDtype = float16` (the live weights, no FP32 shadow)
  and admits chunks 1–64. Earlier documents keep their bytes; `tests/test_golden_identities.py` still passes.
- One `IntegerDecoderGraph` per live model, cached; contexts 512/1024/2048/4096 capped by the model's position limit.
  A strict recipe is the GPU opt-in inside the managed worker (`reference_ops.managed_opt_in`); experiments still need
  `HETEROES_GPU_ACCEPTANCE=1`.
- Generation settings from the pinned generation config (`compact_decode.decode_settings`): EOS ids, pad, repetition
  penalty; other processors and sampling are refused.
- Failures: memory budget → `OUT_OF_MEMORY` (existing smaller-chunk retry), transport timeout → `OTHER` marked
  infrastructure, strict arithmetic → `OTHER`; restore always runs first. Never a reward.
- Managed runs: only a strict run carries `evalDtype`/`evalChunks` into its documents, so earlier managed runs resume
  with identical documents.

## Checks

- `tests/v3/test_v3_strict_decoder.py`: 18 tests, 3 on the GPU. On the 5070 Ti: executor candidates (±) use the live
  weights, restore exactly, equal texts at chunk 1 and 4, no FP32 parameters; generation settings equal the CPU
  B22 oracle with repetition penalty 20 (and differ from penalty 1); unsupported RoPE scaling is refused.
- Mutation: [checks/mutation-01.log](checks/mutation-01.log), **11 of 11 killed** (`acceptance/mutants/strict-decoder.json`;
  one survivor in the first run led to the load-time check test).
- CPU: v3 CPU-guard, golden identities and executor tests pass (82 passed).

## What this does NOT show

No managed lab run with this decoder yet (M5), no lab/SDK/UI option to choose it (M4), no cross-host executor run
beyond the acceptance suites. A nonfinite strict result stalls that candidate as a failure rather than scoring it.
