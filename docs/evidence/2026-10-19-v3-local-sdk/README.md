# Recipe v3 — experiments on one machine: local runner, command line and Python SDK

Baseline: `67c136e` (handoff update after the protocol step), branch `feat/extensibility-step0`. The owner chose "Runner + SDK/CLI"
next. This adds the way a researcher designs and runs an experiment without the web or the desktop apps: their model,
their dataset columns, their reward (Python or declarative), their weight space and sampling, run by the lab's own
coordinator, workers, HTTP protocol, ledger and scoring.

## What changed

- `heteroes/v3/data.py`: datasets with any plain columns and a prompt column (JSON, JSONL, CSV), seeded 80/10/10 splits,
  leak check, content/split hashes, and the Recipe v2 batch sampler.
- `heteroes/v3/model.py`: any local safetensors model pinned by the SHA-256 of its files (no list of names; code and
  pickled weights refused), loaded in FP16 without remote code; the trainable schema of full, subset and LoRA spaces.
  `study/models.verify` now shares its file check (`verify_files`) instead of a copy.
- `heteroes/v3/run.py`: `RecipeV3Run` (what the coordinator, executor and worker runtime read), `build_documents` (recipe
  and plan from a user configuration, every default written out), the coordinator-side scorer of a run, Python scorer
  loading with its code hash. The generation context freezes sigma, batch, scorer and coefficient rule (ADR-008 Q3).
- `heteroes/v3/local.py` (`run_local`), `python -m heteroes.v3 run spec.json`, `heteroes/sdk.py` (`ESConfig`,
  `ESTrainer`, `@reward("name@version")`), and the guide `runtime/docs/v3-local-runs.md`.
- `study/evaluation.generate_rows`: a null system prompt sends only the user turn, and a row without `answer` is never
  counted correct (Recipe v2 rows always have both, so v2 behaviour is unchanged).
- `model/lora.py`: the PEFT configuration no longer requires `initialAdapterSha256`, which exists only after the initial
  adapter is made.

## What the tests show (`runtime/tests/v3/test_v3_local.py`, `test_v3_data_run.py`; tiny Qwen2 and BPE tokenizer built offline)

For full + antithetic, subset and LoRA + antithetic runs (2 generations, 4 candidates, 2 worker threads, real HTTP):
every committed reward equals the scorer applied again to the texts stored in the ledger and the rows of that generation's
batch; the recorded version-2 updates, replayed by hand on a freshly loaded model, give every recorded child hash bit for
bit; the ledger holds (seed, +1), (seed, −1) pairs exactly when antithetic sampling was chosen; with a subset or LoRA every
other parameter is bit-identical to a fresh load. The command line runs a spec with relative paths; the SDK pins a reward
function by its file's SHA-256 and its `@reward` name and version, and refuses lambdas and ambiguous calls.

## Receipts

| Check | Result | File |
| --- | --- | --- |
| Full CPU product check | 22/22 PASS; runtime 2,231 passed, 100 skipped; backend 287 passed (a first run, `check-all-first.log`, failed one backend test: the SDK docstring named the pinned model; fixed) | `check-all.log`, `checks/` |
| Mutation check | control passes; 12/12 killed (`mutation-first.log`: a NaN gap, then a 900 s timeout; fixed with a read_rows test and 30 s run timeouts) | `mutants.json`, `mutation.log` |

## What this does NOT show

No real model or GPU: the tiny model's texts are meaningless, so nothing here says that an experiment learns. No remote
workers (the product's web, agent and desktop are not on v3 yet), no audit scheduling, no Windows.
