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
ESTrainer(args, scorer={"name": "choice-letter", "config": {"answerField": "answer"}})                    # A-D
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

- One machine. Running the same documents on a lab with remote workers is the product's job (web and agent, not yet on v3).
- LoRA needs PEFT (`pip install peft==0.21.2`, the runtime's `lora` extra). LoRA runs are a different search distribution:
  do not compare them on one chart with full-parameter runs.
- GPU runs and learning results are not shown by the tests, which use a tiny model on the CPU.
