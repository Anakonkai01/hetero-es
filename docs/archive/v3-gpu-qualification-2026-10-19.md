# Preregistered Recipe v3 GPU qualification — 2026-10-19

Written before these runs. This is engineering acceptance, not a learning comparison.
The owner authorized the local RTX 5070 Ti and SSH computation on thaonguyen's RTX
3060 (WSL2). The lab's device approval, deployed source and contribution remain unchanged.

## Fixed protocol

Use `runtime/scripts/v3_gpu_acceptance.py run --gpu`, gated by
`HETEROES_GPU_ACCEPTANCE=1`. Pin Qwen/Qwen2.5-0.5B-Instruct at
`7ae557604adf67be50417f59c2c2f167def9a775`, with independently hashed local files.
Torch 2.13.0+cu132, Transformers 5.17.0, NumPy 2.5.3, PEFT 0.21.2.

Each GPU runs full, subset (q_proj weights in layers 20–23), then LoRA (q_proj/v_proj,
rank 4, alpha 8, adapter seed 7). Each cell: two workers and one coordinator through
loopback HTTP; 2 generations, population 4, antithetic pairs, canonical CPU noise,
sigma 0.001 constant, ES alpha 0.001, zscore@1, FP32 evaluation, greedy generation,
16 new tokens, null system prompt. Dataset: 20 distinct arithmetic prompts generated
by the checked-in script; deterministic split seed 42, batch size 4, batch seed 11;
last-integer scorer against the answer column. Every candidate is audited on the
other worker (forced 100%, compared with the product default 5%).

## Acceptance and failure handling

For each of six cells: all 8 candidates commit texts; independent re-scoring equals
all committed rewards; all 8 cross-worker audits match; independently applying every
recorded update on a fresh CPU model gives the GPU child hashes. Compare each space
between the GPUs: source tree, recipe, plan, candidate identities, raw texts, rewards
and both child hashes must be identical. Differences fail the corresponding cell;
preserve the first result before investigating and never silently rerun a failed cell
as if it passed. OOM, driver and scorer failures remain infrastructure/errors, never
reward zero. Report non-noop generation counts; a short run with constant rewards
cannot demonstrate effective updates or learning.

Remote CUDA initially crashed while resolving Linux NVIDIA 580 PTX libraries against
the Windows WSL driver. Qualification processes use a scoped LD_LIBRARY_PATH pointing
to the Windows-provided WSL driver and /usr/lib/wsl/lib. No system driver packages,
services or persistent environment are changed. PEFT is installed into a new private
qualification-only dependency directory, leaving the existing virtualenv untouched.

## What this does NOT show

No 1660 SUPER qualification, native Windows acceptance, installer acceptance, live-lab
distributed acceptance, flag-day deployment or learning benefit. This small arithmetic
dataset and two generations provide no research comparison between full and LoRA.
A subsequent learning experiment requires its own preregistration, larger evaluation,
independent seeds, resource budget and separate reporting for each weight space.

## Pre-generation configuration correction

The first launch on both GPUs stopped during plan validation: last-integer@1
accepts an empty config, rather than answerField. No candidate was opened or
reward observed. The corrected script uses an empty scorer config and integer
answers (matching that scorer's contract). A failing CPU regression check was
added before correction. The fixed protocol, sample size and acceptance criteria
above remain unchanged; initial launch logs are retained separately.
