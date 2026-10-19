# G6: profiles of the two GPUs after the audit (07/10/2026)

Produced by `scripts/profile_worker.py` on the code of the branch `feat/audit-hardening-g6` (the `git_commit` of each file says which commit; the
5070 Ti file is marked dirty because `notebooks/floating_point_testing.ipynb` is untracked and unrelated). Workload: the frozen 16-prompt arithmetic
set, `Qwen2.5-0.5B-Instruct@7ae55760`, sigma 1e-3. Both machines ran the SAME torch (2.13.0+cu132) and transformers (5.17.0): the 5070 Ti in the conda
environment `heteroes-match` (NumPy 2.5.3; the 1660S has 2.5.2, which does not matter: the noise is checked by its fingerprint, not by a version).
Before G6 the two machines had different torch and transformers (`../2026-10-07-g4-profiles/`), so a difference between them could not be blamed on the hardware.

| file | what it is |
|---|---|
| `profile-5070ti.json` | the 5070 Ti, FP16 evaluation, chunk 1 (chunks 1 and 2 probed with 4 candidates). Its update was timed with 8 noise threads and the first version of the update code (0.63 s per candidate); the final code does 0.30 s per candidate with 16 threads (see `profile-5070ti-fp32-chunks.json`). |
| `profile-1660s.json` | the 1660S, FP16, chunk 1, with the synchronization of the OLD worker code (transfer 8.5 s, load 4.0 s, "rehash" 9.3 s: the file was hashed twice and the model once). |
| `profile-1660s-sync2.json` | the 1660S again after the synchronization was changed (one hash, computed while the bytes arrive; the model is compared with the file instead of hashed): transfer 8.46 s, load 0.47 s. Its "rehash" of 4.9 s still contains the creation of the executor (which hashes the model once) because the script timed it that way; the script was then corrected to time `reset_parent` alone, as a running worker does it, and measures about 1 s (snapshot 0.65 s plus the comparison 0.41 s, timed apart on the 1660S). |
| `profile-5070ti-fp32-chunks.json` | the 5070 Ti with `--eval-dtype float32`: chunks 1, 2, 4, 8, 16 compared with chunk 1 on the parent and on 32 perturbed candidates (33 states): **all identical, safe chunk 16**. The update was timed at 1, 2, 4, 8 and 16 candidates and fitted: 0.296 s per candidate plus 0.022 s (residuals below 0.06 s), 16 noise threads. `peak_bytes_candidate` (about 5 GB) is too high: this file was measured before the script freed the FP32 copy it uses for the probes (two copies were alive); one FP32 copy is 2 GB and the peak with one copy is about 3.1 GB (the chunk probes show 3.03 to 3.1 GB). |

## What was measured

| | 5070 Ti | 1660S |
|---|---|---|
| candidate, FP16, chunk 1: perturb / rollout / restore | 1.61 s: 0.75 / 0.72 / 0.14 (G5: 4.5 s: 3.67 / 0.72 / 0.14) | 11.4 s: 3.70 / 7.22 / 0.49 (G5: 17.1 s: 9.24 / 7.35 / 0.49) |
| candidate, FP32, chunk 16: perturb / rollout / restore | 1.02 s: 0.72 / 0.165 / 0.14 | not profiled with FP32 chunk 16 here (see `../2026-10-07-g6-benchmark/`) |
| update on the coordinator | 0.30 s per candidate (G5: 4.4 s) | not its job |
| full synchronization from the 5070 Ti over the cable | none | about 10 s: transfer 8.46 s (116 MB/s, the link) + load 0.47 s + about 1 s (G5: 21.9 s) |

The CPU noise generation was 77 percent of a generation in G5 (3.67 s of 4.5 s per candidate, and the same again inside the update): with a thread pool
that keeps the order of the arithmetic it is 0.72 s per candidate and the update is 15 times faster, with identical weights hashes
(`docs/numerical-contract.md` section 14). What is left on the 1660S is its GPU (rollout 7.2 s, 10 times slower than the 5070 Ti) and its CPU
(3.7 s of noise against 0.75 s on the i7-14700KF; it is a 2012 Xeon E5-2670 without SHA extensions, 3.6 s per SHA-256 of the weights).

## Replay (C4) is not worth it on this CPU

Replaying the update on the 1660S instead of downloading the new weights costs one noise generation per candidate on that CPU: 3.7 s each. A
synchronization costs about 10 s whatever N is. Replay would win only for N <= 2 and only if it ran while the coordinator computes its own update; for the N of
the benchmarks (8 to 24) it loses by a factor of 3 to 9. This is arithmetic from the measured numbers above, not a run.
