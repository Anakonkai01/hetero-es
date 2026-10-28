# Effect of vLLM cross-GPU differences on rewards and ES coefficients

Owner request: measure whether the observed differences matter, finish this survey, record it, then return
to optimizing HeteroES's own strict kernels toward vLLM performance. This survey does not replace that goal
with a vLLM wrapper or waive the cross-GPU output contract.

## Result and interpretation

The differences are often only text, but some change scored answers. On the more realistic Qwen chat
follow-up, **7/576 scored outputs (1.22%) change reward** between the 5070 Ti and 3060; all seven answers
finished before the cap. Each candidate's mean score changes by at most **1/64 = 1.5625 percentage points**.
The best candidate stays the same in this eight-candidate cohort; four pairwise ties change status.

The resulting antithetic coefficients also change. For this follow-up, the cosine of the linear update
proposal projected onto one fixed canonical noise chunk is **0.9565 for z-score** and **0.9383 for centered
rank** (about 17 and 20 degrees). Exhaustively recombining all 256 measured candidate-to-GPU assignments
does not find a different best candidate or a worse cosine in this cohort. This is an offline coefficient/
sampled-direction sensitivity calculation, not an applied model update or learning result.

Thus the accuracy effect is small in this finite sample, but it is not zero and it reaches ES coefficients.
It does not establish negligible impact over a training run. The zero-difference strict contract remains
unmet by this vendor path; the owner has explicitly resumed the own-kernel optimization goal.

## Historical 208-prompt reanalysis

The immutable 2026-10-24 Qwen receipts already contain complete token streams. We decoded them with the
pinned local tokenizer and computed answers for the deterministic word-problem generator. Three free-form
prompts have no expected answer, leaving 205 scored rows. The two existing project scorers agree on these
observations. A second implementation independently reproduces all eight mode/layout/scorer summaries.

| Historical execution | Token-different prompts / 208 | Different answers / 205 | Reward flips / 205 | Correct on 5070 Ti / 3060 |
| --- | ---: | ---: | ---: | ---: |
| Default, one at a time | 15 | 3 | 2 | 98 / 98 |
| Default, batched request | 24 | 9 | 6 | 100 / 96 |
| Batch-invariant, one at a time | 15 | 6 | 6 | 100 / 100 |
| Batch-invariant, batched request | 15 | 6 | 6 | 100 / 100 |

Equal total accuracy can conceal opposing per-prompt reward flips. The default batched total differs by
4/205, or 1.95 percentage points. These old receipts are parent-only and cannot demonstrate candidate
ranking or update effects. They retain their original workloads and throughput limitations.

## New paired candidate experiment

Both hosts consume the same CPU-frozen token/answer manifest. Three pinned trained models are measured
sequentially per GPU, with one vLLM model owner and CPU snapshot. HeteroES exposes canonical HF parameter
views over vLLM storage. We verify equal schema/model files/parent and every candidate weight hash across
hosts, exact final restoration and equal parent/restored streams within each host.

Parameters: vLLM 0.32.0, FP16, greedy temperature 0, sampling seed 0, batch 32, context 1024, prefix cache
disabled/reset, FlashInfer sampler disabled, max 256 output tokens with EOS stopping. Candidate seeds
7001–7004 each use canonical plus/minus sigma 1e-3. The existing noise/ES/scorer code is unchanged. No
coefficients are applied. Parent plus eight candidates supply each total below; restored parent is checked
separately rather than counted again.

The corpus has 208 historical prompts plus the first 64 locally cached GSM8k test rows: 272 prompts, 269
scored. It is a fixed convenience sample. The Arrow file is pinned by SHA-256; its cache directory identifier
`740312...` is not independently verified as an upstream VCS revision, despite that label in the initial
slice metadata. No dataset or model download was needed.

| Model, 256-token raw-prompt corpus | Token-different rows / 2448 | Reward flips / 2421 | Largest candidate score difference | Strict candidate-pair inversions / 28 |
| --- | ---: | ---: | ---: | ---: |
| Qwen2.5-0.5B | 303 | 51 | 2.23 percentage points | 1 |
| SmolLM2-360M | 5 | 0 | 0 | 0 |
| TinyLlama-1.1B | 41 | 1 | 0.37 percentage points | 0 |

The best candidate stays the same for all three models. Smol has almost entirely zero rewards (all zero on
GSM8k); that is weak/no quality signal, not evidence that vLLM is generally harmless on Smol. Tiny also has
low accuracy. Outputs across candidates share prompts and are not independent statistical samples.

Qwen's combined-corpus projected proposal cosine is 0.9944 (z-score) / 0.9878 (rank); the worst mixed-GPU
assignment gives 0.9920 / 0.9878. Its raw GSM8k subset is more sensitive, but 422/576 and 420/576 outputs
hit the cap, and all nine reward flips there involve a capped output. This motivated the follow-up below;
we do not describe those nine cases as completed wrong final answers. Of Qwen's 51 combined reward flips,
24 have both outputs completed and 27 involve the cap. Tiny's single reward flip involves the cap.

## Qwen chat/512-token follow-up

The same 64 GSM8k questions/answers are passed through the pinned Qwen chat template with a system
instruction to finish `Answer: <number>`. The output cap is 512; all other candidate/GPU controls are kept.
Parent plus eight candidates give 576 scored rows. Only 17 and 18 outputs hit the cap, respectively.
All seven reward flips have both outputs completed. Parent accuracy is 31/64 on both GPUs.

| Candidate | 5070 Ti correct / 64 | 3060 correct / 64 |
| --- | ---: | ---: |
| 7001 + | 21 | 20 |
| 7001 - | 20 | 20 |
| 7002 + | 24 | 24 |
| 7002 - | 23 | 23 |
| 7003 + | 23 | 23 |
| 7003 - | 27 | 26 |
| 7004 + | 28 | 28 |
| 7004 - | 24 | 23 |

82/576 token sequences differ. The maximum candidate mean-reward delta is one answer, not seven answers
per candidate. There are no strict pair inversions here, but four ties are created/broken. Some pair
coefficients change from zero to nonzero. No opposite-sign nonzero antithetic coefficient was observed
between the all-5070-Ti and all-3060 cohorts.

## Analysis, controls and source scope

The analyzer uses the existing `last-integer`/`answer-line-last-number` parsers and current float32 z-score
and centered-rank coefficient rules. It merges antithetic coefficients with the existing implementation.
Every one of 2^8 candidate placements is a counterfactual recombination of the measured GPU scores.
Direction cosines use the Gram matrix of exactly one canonical 262144-element chunk from parameter 0 for
each seed. They describe the linear proposal before FP16 publication, momentum or optimizer effects;
they are neither a full-model gradient measurement nor a simulation of multiple learning generations.

Ten synthetic tests cover text-only changes, opposing reward flips hidden by an equal mean, misalignment,
flat/no-signal cases, small reward changes reversing a proposal and mixed-device bias hidden by all-one-GPU
evaluation. Four scratch mutants are killed. Runtime source matches the preceding selected 141-file
manifest on both hosts. Only analysis/probe scripts, evidence and handoff documentation change here;
product/full-package checks from the preceding source are not rerun or relabeled as new acceptance.

The failed initial local probe log is retained: workload construction was launched before extraction of
the cached Arrow slice completed, so it failed before any measurement. Correct local receipts are attempt
02; remote attempt 01. The subsequent dependency was awaited before retry. Intermediate failures and
the 256-token cutoff findings are preserved. `remote-01/` is an intermediate log/source snapshot;
`remote-final-01/` retains completed remote logs and the exact executed harnesses.

## Current vLLM and native Windows survey

Official documentation checked on 2026-10-26 states that upstream vLLM lacks native Windows support;
WSL and community forks are alternatives. Those forks were not examined in this survey.
[Official GPU requirements](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/#requirements).
Its reproducibility documentation limits the guarantee to the same hardware and version. Batch invariance
addresses batch size/order, not a heterogeneous-GPU identity.
[Reproducibility](https://docs.vllm.ai/en/latest/usage/reproducibility/),
[batch invariance](https://docs.vllm.ai/en/latest/features/batch_invariance/).

HeteroES strict checkpoint `3fd704a5` previously passed 452 selected tests on native Windows 11/RTX 3060;
four pinned tiny layouts, B14/B22 and changed/restored states match Linux. This historical receipt does not
qualify the latest source, large trained models or native installers. It remains a concrete reason to
continue the portable strict kernel work.
[Native receipt](../2026-10-25-attention-tree/native-windows-comparison-01.json).

## What this does NOT show

No learning run, applied update, long-run convergence effect, broad quality guarantee, universal support,
vLLM native-Windows acceptance or permission to weaken D2/D3. The installed engine and source are pinned;
other versions/backends can behave differently. No deployment, push/merge or device-state change.
