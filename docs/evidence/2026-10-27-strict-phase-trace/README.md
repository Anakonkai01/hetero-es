# Strict worker phase trace and memory map (M0), 2026-10-27

`acceptance/probes/strict_phase_trace.py` at commit `f325fa06` (source tree `src-ce85ca0a…`), run through
`scripts/accept.py` (perf check `strict-phase-trace`, receipts `docs/acceptance/receipts/2026-10-27T1753-local-perf.json`
and `…T1754-3060-wsl-perf.json`). Trained Qwen2.5-0.5B-Instruct, `strict_b22_v1`, 32 prompts per candidate, chunk 32,
up to 128 new tokens, 6 antithetic pairs (seed 7001+, sigma 1e-3, default CPU noise engine), full weight space.
Every phase is synchronized before and after; CUDA peaks are reset per phase.

| Phase (mean s / CUDA peak GiB) | RTX 5070 Ti (Linux) | RTX 3060 (WSL2) |
| --- | --- | --- |
| load (verified files → GPU) | 1.42 / 0.93 | 2.23 / 0.93 |
| strict engine build | 0.69 / 0.93 | 0.91 / 0.93 |
| first pair rollout (shape capture) | 4.15 / 1.23 | 6.74 / 1.23 |
| warm perturb | 0.72 / 1.14 | 0.77 / 1.14 |
| warm rollout | 0.26 / 1.22 | 0.60 / 1.22 |
| warm restore | 0.14 / 1.15 | 0.19 / 1.15 |

Memory map (both hosts): live FP16 weights 0.93 GiB (292 storages, no FP32 parameter on the GPU), strict engine
buffers 139 MiB, CPU restore snapshot 942 MiB, process host peak 2.65 GiB, CUDA peak 1.23 GiB.
The 12 candidate text hashes, the recipe hash and the parent hash are **equal on the two GPUs**.

Findings:
- With this short workload, perturbation (CPU canonical noise, then copy to the GPU) costs about 3× the warm rollout
  on the 5070 Ti. It is the largest per-candidate stage; the CUDA noise engine or overlap is the place to look.
- Early warm candidates are slower when the decoder meets a new compacted batch shape (first capture); steady state is
  reached after a few candidates.

## What this does NOT show

- Not network transfer, coordinator scoring, the update/publication, audits or scheduling (M5 measures the full run).
- One model and workload; numbers move with prompt length, tokens and rows. Synchronizing each phase adds a little.
- Not native Windows (the probe uses the Unix `resource` module) and not a throughput claim (see `strict-throughput`).
- Host peak is the whole process (model load, tokenizer, CPU snapshot), not a per-role isolation.
