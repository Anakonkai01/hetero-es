# Running your own ES experiment (Recipe v3, one machine)

Recipe v3 (ADR-008) lets you choose the model, the data, the reward, the weight space and the sampling without editing
the runtime. This guide runs an experiment on one machine with the lab's own coordinator, workers, HTTP protocol, ledger
and scoring (`heteroes.v3.local`). Nothing is sent anywhere.

## Python

```python
from heteroes.sdk import ESConfig, ESTrainer, reward

@reward("keyword-hit@1")                     # name@version; the SHA-256 of this file goes into the plan
def keyword_hit(completions, rows):          # one finite score per row; a candidate's reward is their mean
    return [float(row["keyword"] in text) for text, row in zip(completions, rows)]

args = ESConfig(
    model_path="models/qwen2.5-0.5b-instruct",  # a local safetensors model directory (no code, no .bin files)
    model_id="Qwen/Qwen2.5-0.5B-Instruct",
    train_dataset="data/questions.jsonl",        # .jsonl, .json or .csv; any columns plus a prompt column
    prompt_field="question",
    population=16, generations=50, sigma=1e-3, alpha=1e-3, batch_size=32,
    antithetic=False,                            # (seed, +1), (seed, -1) pairs when True; population must be even
    weight_space={"kind": "full"},               # or {"kind": "subset", "include": [r"layers\.2[0-3]\."]}
)                                                # or {"kind": "lora", "rank": 8, "alpha": 16, "targetModules": ["q_proj", "v_proj"]}
summaries = ESTrainer(args, reward_func=keyword_hit).train("runs/first", device="cuda")
```

A reward function must be a named function at the top level of a `.py` file. If it fails or returns a score that is not
a finite number, the generation stops with `ScoringFailed`: a broken reward is never scored as 0.

Without code, use a declarative scorer (the only kind a shared lab accepts):

```python
ESTrainer(args, scorer={"name": "answer-line-last-number"})                      # "Answer: <number>" vs column answer
ESTrainer(args, scorer={"name": "exact-string", "config": {"answerField": "label", "strip": True, "casefold": True}})
ESTrainer(args, scorer={"name": "regex", "config": {"pattern": r"Answer: (\w+)", "answerField": "answer"}})
ESTrainer(args, scorer={"name": "choice-letter", "config": {"answerField": "answer"}})                    # A-E
```

## Command line

```bash
PYTHONPATH=runtime/src python -m heteroes.v3 run spec.json --out runs/first --device cuda --workers 1
```

`spec.json` is the dictionary `ESConfig.to_config(scorer)` returns. Relative paths are read from the spec's directory:

```json
{
  "model": {"path": "models/qwen", "id": "Qwen/Qwen2.5-0.5B-Instruct"},
  "data": {"path": "questions.jsonl", "promptField": "question", "batchSize": 32, "batchSeed": 11, "splitSeed": 42},
  "weightSpace": {"kind": "full"},
  "sigma": {"kind": "constant", "initial": 0.001, "minimum": 0.001},
  "antithetic": false, "maxNewTokens": 256, "systemPrompt": null, "evalDtype": "float32", "decoder": "hf_generate",
  "population": 16, "generations": 50, "alpha": 0.001, "coefficientRule": "zscore@1",
  "scorer": {"kind": "python", "name": "keyword-hit", "version": 1, "path": "reward.py", "function": "keyword_hit"}
}
```

## What the run directory keeps

For controlled repeats, set `candidate_seed_namespace="baseline-id"` in `ESConfig`, or
`"candidateSeedNamespace": "baseline-id"` in the JSON configuration. The same namespace, generation and candidate index
choose the same seeds across different run IDs and worker counts. An omitted namespace preserves the existing rule
(the run ID; `local` by default for this one-machine runner). Candidate seeds are still stored explicitly in the ledger;
recipe/plan documents, noise, update arithmetic and replay are unchanged. Greedy texts can still differ across hardware
in a near tie; use the audits and compare the recorded rewards and child hashes.

| File | What it is |
| --- | --- |
| `recipe.json` | What every worker must agree on (model files, trainable schema, noise, sigma, prompt, data). Its hash is in every candidate. |
| `plan.json` | The coordinator's choices: population, generations, alpha, coefficient rule, scorer (with its code hash). |
| `dataset.json` | The rows, their seeded 80/10/10 splits and their hashes. |
| `ledger.sqlite` | Every candidate, attempt, reward **and the texts it was scored from**, and every update record. |
| `published/` | The weights of the trainable part after each generation (only the adapters for LoRA). |
| `events.jsonl` | What the coordinator and the workers did, with timings. |

The stored texts let you re-score a run with another reward without generating again; the update records (seeds, signs,
coefficients, alpha) let anybody replay the run to the same weights, bit for bit (`tests/v3/test_v3_local.py` does both).

## Limits

- This CLI/SDK runner is for one machine. The staged managed v3 path is documented in `v3-product-runs.md`; it is not deployed to the live lab.
- LoRA needs PEFT (`pip install peft==0.21.2`, the runtime's `lora` extra). LoRA runs are a different search distribution:
  do not compare them on one chart with full-parameter runs.
- Unit tests use a tiny CPU model. Separate Qwen GPU qualification and its limits are recorded in `../../docs/evidence/2026-10-19-v3-gpu/`; it does not establish learning benefit.

## Model registration manifest

Build the lab's registration JSON directly from a downloaded safetensors snapshot:

```bash
heteroes manifest models/my-model --model-id my-org/my-model --revision <40-character-commit> --out my-model.manifest.json
```

The helper streams SHA-256 over every loadable file, rejects executable code and pickled weights, and requires model
and tokenizer files. It accepts arbitrary model IDs for Recipe v3. Omit `--out` to print JSON; an output file must be new
and outside the model directory so the manifest does not change the files it pins. Upload that JSON in the web model
registration form. Device qualification is a separate step; creating a manifest does not qualify any machine.

## Installed CLI and runnable example

In a dedicated environment with the verified Torch/Transformers/NumPy dependencies
already installed, install the local SDK with `python -m pip install --no-deps -e runtime`.
Use `heteroes run spec.json --out runs/first`, `python -m heteroes run ...`, or the
original `python -m heteroes.v3 run ...`; all three use the same runner. Default device
is CPU. An explicit `--device cuda` selects CUDA. In this repository GPU work also
requires owner authorization and `HETEROES_GPU_ACCEPTANCE=1`.

`runtime/examples/v3/train.py` is a runnable SDK example with a separate
`keyword_reward.py`. Supply a safetensors model directory and JSON/JSONL/CSV with
`question` and `keyword` columns (at least ten distinct prompts for seeded splits):

```bash
PYTHONPATH=runtime/src python runtime/examples/v3/train.py \
  --model-path /models/my-model --model-id my-org/my-model \
  --dataset questions.jsonl --out runs/keyword --device cpu
```

`--lora` selects the example's q_proj/v_proj adapter configuration and requires the
pinned PEFT extra. Edit ESConfig for another model's target modules, subset patterns,
sigma schedule, population and batch. The example is a short mechanics check;
meaningful experiments need a defined evaluation and adequate independent runs.

## Python reward execution and identity

Python rewards run directly in the coordinator process with its permissions. Imports
also execute there. There is no sandbox. Use trusted code on your own coordinator;
the shared lab accepts declarative scorers only. Define a named top-level function
in a saved `.py` file; notebook-only functions, lambdas and closures are not supported.

Return one finite numeric score per row in the input order. The coordinator averages
these scores. An exception, NaN, infinity or wrong-length result aborts scoring; it
never becomes reward zero. The plan hashes the scorer source file. Changes to imported
helper modules, package versions, external services or mutable files are not all
captured by that one hash: freeze and record those dependencies for reproducibility.
Avoid time, unseeded randomness and network-dependent scoring in reproducible runs.

## Evaluate and compare recorded checkpoints

```bash
heteroes eval runs/first --model-path models/qwen --generations=-1,9,29 --split test --out evaluation.json
heteroes eval runs/first --model-path models/qwen --generations=29 --split test \
  --samples 32 --ks 1,16,32 --seed 11 --temperature 0.6 --out sampled.json
heteroes compare baseline.json trained.json --generation-a -1 --generation-b 29 --out comparison.json
```

Evaluation reconstructs each checkpoint from recorded updates and refuses a child hash mismatch. It uses the recipe's
precision, prompt format, decoder and chunk. `--rows other.jsonl --rows-scorer scorer.json` evaluates other ordered rows
with a declarative scorer. A plan's Python scorer requires its pinned `--scorer-path` and `--scorer-function`.
The original `runtime/scripts/v3_evaluate_checkpoints.py` delegates to the same implementation.

Reports keep ordered-row and scorer identities, per-row scores, raw greedy outputs and each sampled output/score. Sampling
requires `hf_generate`; the compact decoder is greedy only. Sampling seeds are `seed + sampleIndex * rowCount + chunkOffset`,
and temperature, sample count and k values are recorded. Success means a score exactly equal to 1. Pass@K uses the
[unbiased estimator](https://arxiv.org/abs/2107.03374). Majority votes on the scorer's extracted answer (normalized strings,
numbers or choice letters); unparsed answers have no vote, and ties select the lexicographically smallest answer. Arbitrary
Python/expression scorers vote on the entire completion text. The report preserves every output for independent review.

Comparison refuses different ordered rows, scorers, splits or counts. By default it compares the final checkpoint in each
report; generation flags select others. It reports B minus A mean reward, fixed/broke counts with success defined as
`score == 1`, the [two-sided exact McNemar binomial test](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html)
on those binary successes, and a 95% paired percentile bootstrap interval for the mean reward difference. `--resamples`
(default 10,000) and `--seed` pin the bootstrap. These describe this fixed paired test set, not variation between training
seeds or a proof of generalization; a degenerate interval is possible when every observed paired difference is equal.
An output file must be new.
