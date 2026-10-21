# GSM8K demo on the live r11 lab: three tiers (predeclared)

2026-10-21 night, Asia/Ho_Chi_Minh. Live lab `lab.heteroes.site` at release `93ff85f`. Owner's plan approved in chat
(`~/.claude/plans/a-c-i-n-y-th-nh-prancy-allen.md`). **This file and the three specs were committed BEFORE any run.** Results
go to `RESULTS.md`, and nothing in this file is edited afterwards.

## Members

Coordinator: `5070ti-nhan` (CLI, device `dbe5254b…`, also a GPU worker `cli-71b757062fd9`). Workers: `quang-3060`
(`cli-73b87e369ddc`, WSL), `3060-thao` (`desktop-d9017660e75f`, native Windows app, Tailscale disconnected, so it reaches the
coordinator through the public compute route `compute.heteroes.site`), and `1660s` (`cli-d90d1da024e9`). The **1660S is optional**:
the owner warned that it has a PCI fault and may switch off. Losing it must not fail a run. If it reboots, its contribution
stays OFF (the AI does not turn it back on).

## Common recipe (`tier*.json`)

Qwen2.5-0.5B-Instruct `7ae5576…` (manifest `af52722f…`, qualified on every member), FP32, full weights, one-point
(not antithetic), zscore@1, alpha 5e-4, sigma cosine 1e-3 → 2.5e-4, 512 new tokens, decoder **`hf_fp32_cpu_guard_v1`**
(numerical-contract §17.1: without it, long GSM8K answers flip about 1 text in 768 across GPUs, and a strict audit would
quarantine a member), `evalChunk` 32 on every device, sampler `epoch-shuffle@1`, scorer `answer-line-last-number@1`,
scheduler `greedy-tail`, `allowJoin`, audit rate 0.05 (lab default). Data: `build_gsm8k_dataset.py` from `openai/gsm8k`
`740312a…`, seed 20261020. `v2` = 6,973 train / 500 validation / 1,319 test (train and validation are disjoint draws of
the official train split, test is the official test). `smoke` = the same train with the first 64 validation and 64 test rows.

| Tier | Data | N | Batch | Generations | Validation every | Purpose |
| ---- | ---- | - | ----- | ----------- | ---------------- | ------- |
| 1 smoke | smoke | 8 | 8 | 2 | 2 | r11 smoke run: 4 members, public route, memory fit of chunk 32, full parity |
| 2 stress | smoke | 32 | 32 | 5 | 5 | the four system moments, speed per generation |
| 3 overnight | v2 | 32 | 32 | 300 | 25 | the long run; selection on validation, test once |

## Declared events and pass criteria

- **Tier 1:** COMPLETED, 16 committed results, 0 audit mismatches, no quarantine. Full regeneration on the 5070 Ti
  (texts, rewards, records, both child hashes) equal to the run's. `3060-thao` commits at least one result (public route).
- **Tier 2:** (a) committed results per member per generation reported (uneven split by speed). (b) The notebook turns
  `quang-3060` contribution **OFF once generation 2 is open**, then **ON once generation 3 is open**. It must leave, rejoin
  and commit a result after rejoining. A 10-minute deadline applies to each step. (c) Audits: 0 mismatches, every completed
  audit listed. (d) Parity: the ledger replay rebuilds every child hash, and a full regeneration of one generation is equal.
  COMPLETED with 160 committed results. Minutes per generation measured.
- **Tier 3:** launched only if tiers 1 and 2 pass. Reported: final state, applied generations, audits/mismatches, member
  leave/join, validation every 25 generations, selected checkpoint, then **one** test evaluation of the selected checkpoint
  against the base. Parity: ledger replay of child hashes. Regeneration of a sample: every audited candidate plus one
  generation.

## Stop rules

A parity difference, an audit mismatch, a quarantine, or a declared event not recovered within its deadline in tier 1 or 2
means **no overnight run**: nothing on the lab is repaired by hand, and a handoff is written. In tier 3, a FAILED run or an
audit mismatch is recorded, not restarted. A lost 1660S is recorded, and the run goes on.

## What this does NOT show

This is a predeclaration, not a result. It is one configuration and one seed per tier. The overnight run is one learning
attempt, not a replication of the reference papers (which use 1.5B–3B models, other batch schedules and several seeds). It
does not cover a coordinator or lab crash, nor per-device chunk sizes (backlog item 9).
