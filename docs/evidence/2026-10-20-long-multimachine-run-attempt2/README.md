# Candidate5 long multi-machine acceptance, attempt 2 — 2026-10-20

Recorded before submission. The first attempt is preserved in `../2026-10-20-long-multimachine-run/`.
It stopped at 14 applied generations after operator pauses to relocate large data and a premature diagnosis
of a normal replay-to-sync fallback. It is NOT release acceptance and established no numerical fault.

## Predeclared setup and acceptance

Isolated candidate5 lab only (8790). Thao WSL CPU coordinator `cli-2ffce4b7de39`.
GPU workers: Linux RTX 5070 Ti `desktop-906949218c43`, native Windows RTX 3060
`desktop-9f9da13f0f82`, Quang WSL RTX 3060 `cli-894b5d440398`.
All four devices must be approved, online, contribution ON and unallocated before submission.
Thao large artifacts now resolve to D:/HeteroES-r11-long-data-20261020/artifacts (829 GiB free);
private live ledger, runtime and process records remain on WSL ext4. C: is approximately 10 GiB free;
Quang C: approximately 20 GiB. The local Archive UUID was verified as 10443D1F443D094C, 238 GiB free.

Frozen spec: `spec-thao.json`, `rows.json`, `reward.py`. Qwen2.5-0.5B-Instruct pinned revision,
FP32 evaluation, canonical CPU noise, full weights, antithetic population 8, 50 generations,
batch size 8, 32 new tokens, Python distinct-characters reward, fresh attempt-2 seed namespace.
Managed audit rate 0.05; three eligible GPU workers.

Around generation 20, while Quang holds an uncommitted lease, hard-stop its exact recorded compute PID
and its CLI agent PID (to model a worker disappearance). Wait about 300 seconds, restart the CLI normally,
turn contribution ON for its new boot, and observe whether managed execution returns. Do not manually
edit ledger, assignments, processed-command state or process ownership to make recovery pass.
Record UTC timestamps, per-worker ledger counts, attempts, retry and audit outcomes from detached monitoring.

Acceptance: COMPLETED, all 50 applied children, all texts/completion hashes/rewards and generation
contexts/update records exactly equal on independent CUDA regeneration on the 5070 Ti; zero audit
mismatches, no quarantine; Quang expired/failed attempt followed by committed retry; complete usage and
browser screenshot with no page errors. A replay_failed event alone is not a stop: full-sync fallback is expected.
A demonstrated numerical/audit/distributed/recovery bug triggers the release plan stop/handoff rule.

## What this does NOT show

No learning, generalization, throughput or speedup claim. No public installer publication, merge or live
deployment. This predeclaration is not evidence that the run passed.
