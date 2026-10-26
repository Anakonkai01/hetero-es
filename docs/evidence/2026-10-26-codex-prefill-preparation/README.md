# Superseded sandbox preflight — 2026-10-26

Attempted `scripts/check-all.sh` at `48547ba3` before the owner enabled full permissions.
The restricted session exposed no NVIDIA devices and denied local sockets and subprocesses.
Runtime: 2831 passed, 811 skipped, 211 failed, 180 errors; these are environment failures, not acceptance.
The run was stopped after the permission change. Python lint/format and source imports passed; the
Prettier launcher failed with `spawnSync git EPERM`. A temporary offline-NVRTC test was removed before
implementation; no runtime source was modified in this preflight.

The real continuation is in `../2026-10-26-strict-prefill-attention/` and uses the accessible GPUs.

## What this does NOT show

No numerical regression, GPU acceptance, performance measurement or successful full check.
