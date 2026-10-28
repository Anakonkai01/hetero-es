# Paired Qwen Recipe v3 GPU qualification — 2026-10-19

Preregistered before the runs in `docs/v3-gpu-qualification-2026-10-19.md`
(commit `912b35e`; pre-generation configuration correction `0bbf881`).
The owner authorized both GPUs and SSH to thaonguyen's 3060. No sudo, deployed
lab operation, device approval, existing-environment mutation or publication.

## Result

All six cells passed: pinned Qwen2.5-0.5B-Instruct on RTX 5070 Ti (Linux) and RTX
3060 (WSL2), each in full, subset and LoRA space. Each cell uses a real coordinator
and two HTTP workers on that machine, two generations, four antithetic candidates,
FP32 evaluation, canonical CPU noise and 100% forced audits.

| Space | Candidates per GPU | Cross-GPU texts compared | Audits, both GPUs | Non-noop generations per GPU |
| --- | ---: | ---: | ---: | ---: |
| full | 8 | 32 | 16 | 2 |
| subset | 8 | 32 | 16 | 0 |
| LoRA | 8 | 32 | 16 | 0 |

All **96 cross-GPU text comparisons** match. All **48 audits** match. Recipe,
plan, dataset, candidate identities, rewards, generation records and both child
hashes agree between the GPUs in every space. Independent re-scoring from stored
texts and independent CPU replay of both updates pass in each of the six runs.
Full space exercises nonzero updates; subset/LoRA rewards are constant in this
small qualification and those updates are no-ops.

`compare-{full,subset,lora}.json` are the authoritative paired comparisons.
`{GPU}-{space}.json` contain environment, exact source-file hashes, raw candidate
texts/rewards, child hashes, audit counts and replay results. `*-state.json` retain
recipe/plan/dataset and canonical update records, without attempt credentials.
Private full ledgers and weight/cache files remain in the new qualification run
directories; they are not committed here.

Local private root: `.scratch/v3-gpu-20261019/*-second/`.
Remote private root: `~/projects/heteroes-v3-acceptance-20261019/results/*-second/`.
Runtime source is `0bbf881`; both source-tree receipts agree. CLI/docs changes made
later do not change the source used for these runs. Each final run log completed
before this folder was committed. CPU probe tests cover both GPU gates, comparison
failures and scorer configuration; `mutation.log` kills **5/5** mutants.

## Intermediate failures and environment

The first launches on both GPUs failed plan validation because last-integer@1
requires an empty config. They opened no candidate and observed no reward. A CPU
regression was added before fixing the config and changing answer values to the
integers that this scorer expects. `*-full-first.log` preserve those failures;
final runs used fresh directories. The initial probe test invocation also used a
wrong working directory; the next tests-first receipt exercises the missing code.

CUDA initialization on the 3060 initially crashed before candidate execution:
the Linux NVIDIA 580 PTX library shadowed the matching Windows WSL driver. The
successful processes use a scoped LD_LIBRARY_PATH for the mounted WSL driver;
no driver/package/service change was made. `3060-environment.txt` records the
library inventory. PEFT 0.21.2 was added only to a new qualification dependency
directory with --no-deps; the original remote environment remains unchanged.

Both machines: Torch 2.13.0+cu132, Transformers 5.17.0, NumPy 2.5.3 and PEFT
0.21.2. Python and driver details are recorded per receipt; these are not claimed
to be an identical OS/interpreter stack.

## What this does NOT show

No learning benefit, full-vs-LoRA research comparison, native Windows, installer
acceptance, GTX 1660 SUPER qualification or live-lab deployment. The two GPU runs
are independent loopback runs, not one distributed job across the network. The
sample is 96 texts per GPU, not a general guarantee of numerical portability.
Zero-update subset/LoRA cells demonstrate execution/audit/replay, not effective
optimization. Learning experiments need separate preregistration and reporting.
