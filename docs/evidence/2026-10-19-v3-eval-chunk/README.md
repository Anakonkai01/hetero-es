# Recipe v3 `evaluation.chunk` and first Countdown measurements — 2026-10-19

## Measurements (RTX 5070 Ti, Qwen2.5-0.5B-Instruct snapshot `7ae55760…`, FP32 evaluation, owner-authorized GPU)

`probe_base.py` / `probe-base-64.json`: the base model on the first 64 validation prompts of the 2500-row Countdown
file (`../2026-10-19-countdown-scorer/countdown-2500.jsonl.meta.json`), `countdown@1` scorer, chunk 16:

| maxNewTokens | seconds | correct | format only (0.1) | no answer | truncated | mean tokens |
| --- | --- | --- | --- | --- | --- | --- |
| 512 | 25.4 | 0 | 15 | 49 | 41 | 448 |
| 1024 | 63.4 | 0 | 17 | 47 | 27 | 704 |

`probe_speed.py` / `probe-speed-128.json`: 128 prompts, 512 tokens: `generate()` chunk 16 50.0 s, compact decoder
chunk 16 45.0 s, `generate()` chunk 64 28.1 s, compact chunk 64 25.2 s; all 128 texts identical to `generate()` chunk 16
in every configuration.

## Change

The first v3 documents fixed 16 prompts per `generate()` call without saying so. A recipe may now declare
`evaluation.chunk` (FP32: 16, 32 or 64; FP16: 1). Absent means 16, so every v3 document and hash written before (the
shipped desktop-v3 qualification reference included) is unchanged; `build_documents` writes the key only when
`evalChunk` is chosen (SDK `ESConfig.eval_chunk`, managed `evalChunk`). `CandidateExecutor` uses the declared chunk and
refuses a different explicit one; the device agent no longer passes `--chunk 16` to v3 workers (v1 keeps it).
Tests: `runtime/tests/v3/test_v3_eval_chunk.py`, `runtime/tests/ledger/test_device_agent.py`; mutation 8/8 killed.

## What this does NOT show

- Chunk 64 texts equal chunk 16 on ONE GPU for 128 Countdown prompts; equality across GPUs at chunk 64 for v3/Countdown
  is not shown here (the earlier v1 probes used other workloads). The distributed run's audits will check it.
- The base model's 0/64 correct is a small sample; it says only that the starting reward signal is the 0.1 format credit.
- No ES run; no learning claim. Backend/web do not offer the chunk yet.
