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

Without code, use a declarative scorer:

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

- `run` uses one machine; `serve` and `worker` support separate machines. The staged managed v3 path is documented in
  `v3-product-runs.md`; it is not deployed to the live lab.
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

The local and standalone CLI run Python rewards directly in the coordinator process with its permissions. Imports
also execute there. The managed web lab now accepts Python rewards too, executing them in a coordinator child process
with a time limit; that child process is not a security sandbox. Workers never receive the source. Define a named top-level function
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

## Coordinate separate machines

Install the same runtime and its numerical dependencies on each machine, and put the pinned safetensors model on each
worker. Set the same shared secret in `HETEROES_TOKEN` on coordinator and workers (read it privately; do not put it in
command arguments). The network must be private, such as LAN or Tailscale; this existing HTTP protocol does not provide TLS.

```bash
heteroes serve spec.json --out runs/distributed --host <coordinator-private-IP> --port 8765 --device cuda \
  --worker-ids worker-a,worker-b
heteroes worker --coordinator http://<coordinator-private-IP>:8765 --model-path models/qwen \
  --worker-id worker-a --out runs/worker-a --device cuda --recipe-hash <hash-from-server.json>
```

Run the worker command independently on each worker, using distinct worker IDs and fresh output directories. The
coordinator prints its URL and recipe/plan hashes and writes `server.json`. `--device cpu` lets a CPU coordinate while
remote GPUs generate texts. Native Windows LoRA coordination requires `--initial-adapter <pinned-file>`; it never creates
a random adapter. Full/subset Windows runs use the same pinned base files.

Workers fetch only the recipe, plan and dataset through authenticated `/v1/inputs`, verify dataset hashes, model file
hashes, generation settings and trainable schema, and optionally require the out-of-band `--recipe-hash`. LoRA workers
download the pinned initial adapter over the existing authenticated weights route. A Python reward/coefficient source
stays on the coordinator. Workers synchronize by verified replay and retain a checked full-transfer fallback.

The output includes `inputs.json`, the normal v3 documents/ledger/events, and final `summaries.json`. Worker outputs keep
`identity.json` and `events.jsonl`. SIGINT/SIGTERM requests a cooperative stop. The server retains the terminal job briefly
so external workers can exit normally. All output directories must be fresh. `--token-env` changes the environment
variable name; `--timeout-seconds` bounds each generation. `--audit-rate` defaults to 0.05. The single-machine runner and
the managed web lab continue to use their existing paths.

## Offer a CLI experiment to a lab

Install the Linux `heteroes-worker` first and run its self-test (`--device cpu` for a CPU coordinator, default CUDA for a
GPU). Set `HETEROES_LAB_ACCESS_TOKEN` privately to the lab user's access token. Then:

```bash
heteroes serve spec.json --lab https://your-lab.example --workspace <workspace-ID> \
  --host <reachable-private-IP> --worker-ids gpu-worker-a,gpu-worker-b --device cpu --out runs/lab-offer
```

`--worker-home` selects another installed CLI home. The command pairs that CLI device if needed, starts its existing
agent, and waits for administrator approval in the specified workspace. It uploads the pinned model and dataset through
the lab's normal signed storage routes (including file-backed large datasets), freezes Python source into the plan, and
creates/submits an experiment with this device as coordinator. Qualified GPU workers must already belong to the workspace.
Turn contribution ON in the lab for the current boot; the CLI never approves or enables a device itself. It uses the same
managed coordinator/worker routing, reports and recovery as the desktop app. A paired device's role/address can change
only through the normal configuration API while OFF and drained.

The non-secret `lab-offer.json` receipt binds local input hashes and remote IDs so completed registration steps and the
experiment are reused on retry. Editing a local file requires a fresh output directory. Device credentials remain in the
installed CLI's private token file; user access tokens are read from the environment, never command arguments or receipts.
The managed lab supports its own FP32/CPU-noise recipe choices, fixed Worker port and managed audit/time limits; unsupported
standalone flags are refused. A managed Windows LoRA coordinator remains subject to the lab's pinned-adapter restriction.
This staged route requires the matching r11 lab and is not supported by the public r10 deployment.


## Prompt, boxed answers and usage

The spec/SDK accepts optional `promptFormat` / `ESConfig.prompt_format`: `chat` uses the model's chat template, `raw`
sends each dataset prompt verbatim. Raw requires `systemPrompt: null`. Omitting the option preserves previous recipe
hashes; an explicitly chosen format becomes part of the recipe's evaluation identity.

A declarative scorer `{ "name": "boxed-number", "version": 1, "config": { "answerField": "answer", "formatReward": 0.1 } }`
scores the last `\boxed{plain decimal}`. Correct numeric answers earn 1; valid wrong numbers earn formatReward (default 0,
less than 1); malformed final boxes earn 0. Decimal comparison is exact; grouped commas are accepted, fractions and nested
LaTeX expressions are unsupported. Use the normal declarative kind/codeSha256 fields where a complete scorer is required.

Recipe v3 runners maintain a separate private `usage.sqlite`. Candidate receipts contain generated token counts per row,
device and synchronized execution wall seconds. Generation events, SDK summaries and managed detail pages expose token
and reported GPU seconds. Counts include the first EOS token and omit only later padding. Audit tokens are separate.
GPU seconds sum successful reported CUDA executions (including audits) and the synchronized coordinator GPU update itself (not writing or hashing the child weights); CPU execution adds 0.
Idle time, validation and unreported failures are excluded. This is execution accounting, not power/energy measurement.
Old workers remain usable with partial coverage; retry receipts are deduplicated. These optional receipts do not change
numerical identities, and recovery points include their database when present.
