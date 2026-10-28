# Coordinator update GPU time excludes weight publication (2026-10-20, session 5 review)

Review finding in 46c0834: the usage sidecar billed `applied - recorded` as coordinator GPU seconds. That window also
contains `prepare_publication` (copying the full model off the GPU, writing it and hashing it) and the ledger
`mark_applied` call, so a CUDA coordinator's "GPU seconds" grew with disk speed and model size. Now the coordinator
synchronizes CUDA right after the update and bills only `_apply_record`. The existing `update_seconds` summary field
keeps its previous meaning (update through hashing); only the usage number changed. No numerical file, record or
weight changed.

`before.log` failed for the missing seam; `before-window.log` is the honest pre-fix failure (0.51 s billed while
publication slept 0.5 s); `after.log` has 71 usage/projection/recovery/update-record tests passing; mutation 2/2.

## What this does NOT show

The test runs on CPU with the GPU check and `torch.cuda.synchronize` patched; no real CUDA coordinator timing was
measured here. GPU seconds remain wall time of the synchronized update, not utilization or energy.
