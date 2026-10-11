# ES papers and local implementation decisions

Reviewed versions are pinned so later paper revisions do not silently change the
experiment specification. This document proposes local experiments; it does not
claim replicated paper results or measured learning gains.

## Sources and implications

| Source | Relevant evidence | Local decision |
| --- | --- | --- |
| [Evolution Strategies at Scale, v3](https://arxiv.org/html/2509.24372v3), 14 July 2026 | Full-parameter, forward-only ES; population and noise/learning-rate ablations. | Keep one-point population-normalized ES. Compare populations and count actual rollouts/tokens as well as generations. |
| [Agentic ESOpt, v2](https://arxiv.org/html/2608.17310v2) | Long-horizon agent fine-tuning with a cosine perturbation-scale schedule. | Add a frozen cosine sigma schedule in Recipe v2. Our initial math experiment is a local hypothesis, not replication of its agent benchmarks. |
| [Understanding Evolution Strategies for LLM Reasoning, v2](https://arxiv.org/html/2608.27351v2) | Population-size effects and evaluation of broader reasoning coverage with multiple samples. | Include N=16/32/64, greedy accuracy, sampled Pass@K and majority accuracy; judge generalization using held-out answers. |

Upstream implementations optimize for their environments. HeteroES must retain
CPU canonical noise, exact FP16 parent restoration, FP32 evaluation and recorded
update/replay equivalence across its admitted devices. No upstream perturbation
or restore shortcut replaces those contracts.

## Recipe v2 numerical contract

Preserve the practical update convention
`theta_next = theta + alpha/N * sum(z_i * epsilon_i)`, where `z_i` uses population
reward mean and standard deviation. The explicit `1/sigma` factor from the
classical gradient estimator is absorbed into the configured learning rate;
do not introduce it again when implementing the schedule. Zero reward variance
produces a zero update, never NaNs.

Constant sigma and cosine sigma are separate frozen recipes. For G generations,
index `t=0..G-1`, define cosine endpoints explicitly:
`sigma(t) = sigma_min + (sigma_initial-sigma_min)*(1+cos(pi*t/(G-1)))/2`.
For G=1 use the initial sigma. The G-1 indexing is our local endpoint convention;
record it in the manifest rather than assuming equivalence with paper indexing.
Training sigma stays positive. Save each generation's effective sigma and batch
hash before leasing candidates. Resuming never restarts the schedule.

Recipe v1 serialization and hashes remain unchanged. Recipe v2 must bind model
revision/files, dataset content/splits, prompt/evaluator/decoder, train-batch
sampling and sigma schedule. Operational assignment epochs and backup policy do
not enter numerical seed identity.

## Frozen local comparison

Qwen2.5-0.5B first: 40 generations, batch 32, N=32, alpha=5e-4; constant sigma
1e-3 versus cosine 1e-3 to 2.5e-4, seeds 11/29/47. Add constant N=16 and N=64
ablations. These are chosen local settings, not established optimum values.
Checkpoints are selected using validation alone. Test evaluation happens after
selection is locked; do not choose recipes or checkpoints by test accuracy.

Report greedy test accuracy separately from sampled Pass@1. With M=32 samples
at temperature 0.6 and c correct samples, use
`Pass@K = 1 - choose(M-c,K)/choose(M,K)` for K=1/16/32. Majority answers use the
same numeric normalization, abstain on extraction failure and break ties using a
frozen deterministic rule. Retain predictions, truncations and errors, alongside
baseline and selected checkpoint results. Compare rollout/token counts and wall
time; equal generation counts alone do not make ES variants equally expensive.

Generated math and GSM8K adapters must provide exact answer keys. For GSM8K,
derive validation from source training data and retain the official test split
as held out. A single imported file uses seed-42 80/10/10 splitting; pre-split
imports preserve all three files and reject prompt duplicates across splits.

Do not claim improved learning until repeated seeds and an independently reloaded
Hugging Face export reproduce the selected model's evaluation predictions.
