# GSM8K dataset builder and pre-split local runs — 2026-10-20

- `runtime/scripts/build_gsm8k_dataset.py`: pinned `openai/gsm8k` revision `740312ad…` (license MIT), parquet files
  checked by SHA-256. Train (2000) and validation (500) are a seeded disjoint draw from the official train split; the
  official test split (1319) is kept whole as the held-out test. Rows: `prompt` (question + "end with 'Answer:
  <number>'"), `question`, `answer` (normalized exactly like `heteroes.study.data.answer(..., "gsm8k-v1")`), for the
  `answer-line-last-number@1` scorer. `meta.json`: the files built in `.scratch/gsm8k/v1` (each under 3 MB).
- Local runs/CLI accept `"data": {"splits": {"train", "validation", "test"}}` (relative paths resolved from the spec),
  built as a `pre-split` v3 dataset; the CLI also resolves a python coefficient rule's path.
- Tests: `runtime/tests/v3/test_gsm8k_dataset.py`, `test_v3_eval_chunk.py`. Mutation 8/8 killed after one survivor
  (no shuffle) got a test (`mutation/result-py-first.txt`).

## What this does NOT show

- No model run on GSM8K yet; no base accuracy measured with this prompt.
- The managed lab imports its own split files through the web; this builder only prepares them.
