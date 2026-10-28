# Soak run (declared before submission, 23 Oct ~02:25, attempt 2 after attempt 1 ran out of disk at generation 60)

Candidate15, engine v2 noise made on the GPU (the default), coordinator nhan, workers nhan + nhut + native Windows
3060. Qwen 0.5B FP32, the twenty multiplication rows, last-integer, 24 antithetic candidates, batch 8, 32 new tokens,
600 generations, validation every 50, seed namespace `overnight-soak-2026-10-23`. One declared fault: SIGKILL of nhut's
newest worker process at completed generation 20 (it was not injected in the fault run). `soak-sampler.sh` records GPU
memory/utilisation/temperature and HeteroES process memory on the three machines every 5 minutes.

Accept if the run completes, audits have no mismatch, no worker is quarantined or blocked, memory does not grow without
bound, and an independent ledger replay matches every child hash on nhan (GPU noise) and nhut (CPU noise). If it cannot
finish before ~07:00 it is cancelled and the completed part is replayed and reported as such. System evidence only.

Attempt 2 adds `soak-guard.py`: if nhan's root disk falls below 12 GiB the run is paused through the lab API instead of
failing; the sampler also records nhan's free disk. Attempt 1 is kept in `attempt1-enospc/`.
