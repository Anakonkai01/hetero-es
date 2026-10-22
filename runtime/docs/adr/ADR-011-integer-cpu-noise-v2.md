# ADR-011 — Integer CPU noise v2 and explicit engine admission

Status: decided by the owner, 2026-10-22. CPU v2 first; enabling CUDA in the lab is deferred.

Finding 13 established that NumPy v1's normal sampler calls the host `log1pf`. glibc 2.39 and 2.43 can produce different
FP16 noise in rare tail cases. Historical v1 recipes, records, addresses, fingerprints and arithmetic remain frozen.
New Recipe v3 lab/SDK runs pin `pcg64_u32_to_f16_normal_quantile_v2`; resuming uses the saved recipe, never a new default.
The lower-level v1 APIs retain their old defaults. An unknown engine or wrong fingerprint is rejected before mutation.

## Byte contract

The SHA-256 seed material uses the v2 version string and the same canonical address fields as v1 (candidate seed,
schema hash, parameter index, chunk index and chunk size). Worker, attempt, lease and scheduling metadata are excluded.
The first 16 digest bytes, interpreted little-endian, seed NumPy PCG64. Generate `ceil(n/2)` raw uint64 words, serialize
little-endian, view each as two little-endian uint32 words (low word first), and keep the first `n`.

For each word `w`, `sign = w >> 31`, `u = w & 0x7fffffff`. Let `m_i` be the exact midpoint between nonnegative finite
FP16 values with bit patterns `i` and `i+1`. Threshold `T_i = floor(2^31 erf(m_i/sqrt(2)))`. Include thresholds through the first `T_i = 2^31 - 1`, then stop. Retain all repeats before that cutoff. The magnitude bit pattern is the number of thresholds `<= u` (`bisect_right`), combined with
`sign << 15`. Signed zero is retained; the largest magnitude is 6.234375. This is a finite quantized Gaussian law,
not an exact continuous normal law. Its 32-bit resolution/tail cutoff is part of this version's contract.

There are 17,980 thresholds. Their packed little-endian uint32 SHA-256 is
`e15f542c139cfd415ca9c19805535a64d8666f7d2e584429ac6e278bf9a32e2d`.
`scripts/gen-noise-v2-table.py` generates them offline using Decimal at two precisions and refuses disagreeing floors.
The generated Python module ships in wheels/source archives. Runtime transformation uses integer operations and table
lookup only; neither the host libm normal sampler nor floating-point transcendental functions participate.
The bucket fast path must equal independent scalar `bisect_right` at every threshold and bucket boundary.

Perturbation and update arithmetic/order remain the existing separate FP32 operations with FP16 publication. CPU v2
uses up to eight noise threads by default; v1 retains sixteen. The explicit environment override remains available.
Thread count/block scheduling must not change bytes. The pinned v2 self-test fingerprint is
`e80f079ca06fd3e2fcae7b41583aedd8b407e65c196677d5da54c1dc6de02bb4`.

## Admission and references

Devices report engine-to-fingerprint capabilities after checking both CPU engines. An old report without the map proves
v1 only. Coordination, initial workers, queue dispatch and elastic joins must support the recipe's saved engine.
Model qualification caches and references are engine-bound: the additive v2 tables never rewrite legacy v1 tables.
A CPU coordinator proves the v2 update known answer; a GPU model qualification additionally proves repeated signed
perturbations, exact restore, texts and rewards. The shipped desktop v2 reference covers full model and pinned LoRA.
Native Windows admission chooses the pinned reference for the reported engine. A CPU fixture proves plumbing only.

## Temporary recovery policy

A worker that exits `needs_private_route` is persistently blocked for that run. Other eligible members continue. The
block survives supervisor/coordinator recovery, pause/resume, contribution OFF/ON and rejoin. The UI shows its reason
and that the policy is temporary. An explicit idempotent retry authorizes one new launch; repeated failure blocks again.
Connectivity changes alone do not clear it. A new run evaluates eligibility again. Public-route weight recovery is
future work, not implemented by this decision.

## Verification limits

See `docs/evidence/2026-10-22-candidate14/README.md` for actual acceptance receipts and their status. Golden vectors,
CPU boundary checks, synthetic browser fixtures and same-machine reference construction alone do not establish native
Windows/GPU parity, deployed behavior, learning quality or a speed improvement.
