# The compacting greedy decoder (`hf_compact`) for Recipe v3 (2026-10-20)

`study.evaluation.generate_rows` now dispatches on the evaluation's decoder: `hf_generate` (the library's `generate()`,
Recipe v2 always) or `hf_compact` (`eval/compact_decode.py`, greedy only; a generation config it does not reproduce is
refused before decoding). Recipe v3 options, the run documents, the lab validation and the web form accept it.

CPU tests (`runtime/tests/v3/test_v3_compact_decoder.py`, a tiny random model whose rows end at different steps, with and
without a system prompt): equal texts and compaction really happens. Mutation runtime 5/5, backend 1/1.

GPU probe (`probe_compact.py`): pinned Qwen2.5-0.5B, FP32, 500 GSM8K rows (first 500 of `.scratch/gsm8k/v1/test.jsonl`,
SHA-256 in the receipts), 256 new tokens, chunks of 16, no system prompt, each decoder twice, alternating:

| Device | generate (s) | compact (s) | speed-up | different texts |
| --- | --- | --- | --- | --- |
| RTX 5070 Ti, Linux (`probe-5070ti.json`) | 91.4 / 91.0 | 87.0 / 87.1 | 1.05x | 0 of 500 |
| RTX 3060, WSL2 Quang, pinned CLI runtime (`probe-3060-quang.json`) | 239.4 / 242.9 | 233.0 / 235.9 | 1.03x | 0 of 500 |

Both decoders were also repeatable across their two runs on each device.

## What this does NOT show

- The speed-up at chunk 16 is small (3-5 %): the batch is too small for dropped rows to save much. Larger chunks or
  longer answers were not measured here; the v1 measurements of 2026-10-09 used chunk 64.
- Equal texts on 500 rows is not a guarantee: a near tie can still break differently (numerical contract section 17).
- The 1660S and native Windows were not measured. The first 3060 attempt crashed in CUDA because it was started with
  only `/usr/lib/wsl/lib`; the recorded run used the runtime's own WSL library path (`worker_environment`).
