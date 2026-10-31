# Part A final review acceptance

Source identity `src-ede4338ef54a443a0ecc33a2bc96ea836ea188b856727ed63e095594a7b8b3a4`,
committed source `21d7f591` (source fixes through `a5d81cbd`). All 37 checks passed on this same clean source:
CPU 2/2, local GPU/performance/fault/package/mutation 24/24, RTX 3060 WSL 8/8, native Windows 3/3.
Every copied check log was verified against its original receipt SHA-256 before archival. Receipts are copied without
editing; verified-logs.json maps their original log paths to the immutable archive.

CPU: acceptance selftests 58 passed, runtime 3,324 passed / 1,045 intentionally CUDA-hidden skips,
backend SQLite 464 passed, all 24 check-all steps passed. Full CPU child logs are in
2026-11-01-partA-cpu-ede4338e. GPU noise/ES: 572 passed, zero skips on each of the three GPU environments.
Strict/eval: 1,639 local, 1,560 WSL, 956 native; zero skips. RTX 3060 explicitly deselects 79 SM120-only cases.
Strict Qwen parity passes on all three; Smol/Tiny parity, memory, phase trace and throughput pass on both Linux hosts.
Local short32 reaches 10,100.4 token/s, chat128 9,931.9 token/s, above pinned floors 9,873.1 / 9,753.
Fault/replay, 600-generation soak, int8 lifecycle, both Linux app packages and all twelve mutation groups passed.

P-FROZEN before/after CPU and CUDA bytes and update overhead are retained in 2026-10-31-frozen-fixes.
The final audit rechecks those fingerprints and confirms frozen source is unchanged since 7908609c.
A-014 is the explicitly authorized ledger release-state correction, not an unchanged-state claim.
Network, runtime, harness and documentation proof are indexed in the working branch EVIDENCE-INDEX.md.
The independently measured non-strict SM86 FP16 reference is in 2026-11-01-qwen-fp16-sm86;
the shared strict golden was not changed. Intermediate real failures remain archived in 2026-11-01-partA-matrix-c0d90ddb.

## What this does NOT show

This closes the approved Part A review scope. It does not deploy or restart the live lab, change device approval,
close deferred architecture/full-disk work or the separate managed-runner bookkeeping measurement,
prove PostgreSQL/OIDC/MinIO or MiniCloud acceptance, or show learning. Parts B and C remain to be implemented.
