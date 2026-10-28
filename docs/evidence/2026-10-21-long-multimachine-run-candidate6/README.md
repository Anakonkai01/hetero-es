# Candidate6 managed three-GPU acceptance (predeclared, not started)

2026-10-21 Asia/Ho_Chi_Minh. Candidate6 build `lf1-20261020-r11-candidate6`, source `f5d311b`,
worker runtime `aa74bad820b9677fdaa1f0b81261264479c468c52b90636ae956232049596c38`.
Owner-authorized replacement for the candidate5 audit stop. Exact input spec/reward/rows are included.

Coordinator: Thao WSL CPU `cli-2ffce4b7de39`. GPU workers: 5070 Ti Linux desktop
`desktop-906949218c43`, Thao Windows 3060 `desktop-9f9da13f0f82`, Quang WSL 3060
`cli-894b5d440398`. Contribution must be ON on every current boot before offering the run.
The offer selects the new runtime explicitly and receives the lab access token through stdin.
No token or private ledger is an evidence artifact.

Qwen2.5-0.5B-Instruct, full weights, GPU FP32 + selective CPU reference via the separate
`hf_fp32_cpu_guard_v1` decoder, antithetic population 8, 50 generations, batch 8, max 32 tokens,
sigma .025, alpha .005, zscore@1, declared Python distinct-characters reward. Managed audit rate .05.
The independent verification process must not share the managed parent/checkpoint cache.

Before starting, all four installed-device self-tests must pass and Quang C: must have at least
20 GB free (decimal bytes). Quang is currently unreachable; no experiment has been offered.

## Required acceptance

- COMPLETED, exactly 50 applied generations and 400 candidate results; all three GPU workers contribute.
- Zero audit mismatches and no quarantine; at least one completed audit.
- Around generation 20, hard-stop the identified Quang agent and compute process while a main candidate
  attempt is active. Capture process identity and timestamps; restart after approximately 300 seconds.
  Prove a failed/expired attempt followed by successful retry from the ledger; never infer this from logs
  or count a synthetic zero reward as recovery.
- Independent 5070 Ti regeneration: every candidate text/hash/reward, all generation contexts and
  records, and all 50 child hashes exactly equal. Run both included verifiers; require 50 generations.
- Complete usage receipt and browser screenshot with no page errors.
- Any genuine audit/parity mismatch: pause, drain, collect immutable evidence, hand off and stop.

## What this does NOT show

This folder is a predeclaration. It contains no managed-run, outage, recovery, parity or release pass.
It makes no learning, speedup, arbitrary-model or universal cross-GPU numerical guarantee. The .01
near-tie guard is empirical. No live deployment/publication/approval is authorized by these receipts;
each irreversible flag-day action still requires explicit owner confirmation.
