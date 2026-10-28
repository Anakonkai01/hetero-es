# Candidate5 long multi-machine acceptance — 2026-10-20

## Predeclared run and acceptance

Recorded before submission. Isolated candidate5 lab only, port 8790. Thao WSL CPU coordinator
(`cli-2ffce4b7de39`), GPU workers Linux RTX 5070 Ti (`desktop-906949218c43`), native Windows
RTX 3060 (`desktop-9f9da13f0f82`), Quang WSL RTX 3060 (`cli-894b5d440398`). All must be approved,
online and contribution ON for this boot. Quang candidate5 install completed; CUDA self-test passed;
C: has 20 GiB free before/after setup. Thao C: currently 17 GiB free.

Frozen spec: `spec-thao.json`, `rows.json`, `reward.py`. Qwen2.5-0.5B-Instruct pinned revision,
FP32 evaluation, canonical CPU noise, full weights, antithetic population 8, 50 generations,
batch size 8, 32 new tokens, Python distinct-characters reward, fresh seed namespace.
Managed audit rate is fixed at 0.05 with three eligible GPU workers.

Around generation 20, hard-stop Quang's active compute worker by its exact PID while it owns
an uncommitted candidate lease. Keep it unavailable for approximately 300 seconds, then restart.
Record UTC timestamps, PID, candidate identity and retry evidence. Never manufacture reward zero.
Monitor from a detached process; record per-worker committed counts from the coordinator ledger.

Acceptance requires COMPLETED, 50 applied child hashes, all candidate texts/completion hashes/rewards,
and both numerical generation records equal on independent CUDA re-execution on the 5070 Ti;
completed audits with zero mismatches and no quarantine; an expired/failed Quang attempt followed by
a successful retry; complete usage facts and an experiment browser screenshot without page errors.
A numerical, audit, distributed or recovery fault triggers the release plan stop/handoff rule.

## What this does NOT show

No learning, generalization, throughput or speedup claim. No public installer publication or live
lab deployment. This document declares the test; acceptance remains pending until receipts exist.
