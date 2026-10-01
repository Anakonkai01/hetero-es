# ADR-001 — CPU PCG64 as the canonical cross-worker NoiseEngine

- **Status:** Accepted as *provisional* in MASTER §0/§6 (2026-09-29). This written ADR is a **draft by Claude, pending owner review**.
- **Date:** 2026-09-30
- **Deciders:** A (Systems/Core owner)
- **Related:** [numerical-contract.md §4](../numerical-contract.md), [architecture.md §2](../architecture.md), evidence in `artifacts/probes/2026-09-29/`

## Context

In distributed ES the worker returns only a scalar reward; the coordinator regenerates each candidate's noise ε_i from its seed and combines it with the reward to update the model (architecture.md §2). Worker and coordinator therefore need **bit-identical noise from the same seed**, on different machines. If they disagree, the update silently uses directions that were never evaluated.

The notebook prototype generated noise with native CUDA RNG: a `torch.Generator` on the GPU, `manual_seed(seed)`, then `torch.randn_like(param, generator=g)` over the parameters in order.

Physical probes on 2026-09-29 tested this recipe on the RTX 5070 Ti (compute capability 12.0) and the GTX 1660 Super (7.5), with the same model revision, FP16 dtype, parameter schema, workload and seed:

| Comparison | Noise sample hash | Candidate predictions |
|---|---|---|
| 5070 Ti (torch 2.10/cu128) vs 1660S (torch 2.13/cu132) | DIFF | 8 of 16 differ |
| 5070 Ti **matched** (torch 2.13/cu132, Transformers 5.17) vs 1660S | DIFF | 8 of 16 differ |

Structure, base weights, base predictions and exact restore all matched. Candidate reward matched too (0.25 = 0.25), which shows reward is too coarse to detect the problem.

Additional observation from the same JSON: the 5070 Ti produced the **same** CUDA noise hash (`6839fde5…`) under both torch 2.10/cu128 and torch 2.13/cu132, while the 1660S produced `bd7d3670…`. In this data the divergence follows the machine/GPU, not the software version. (Two data points; not a general law.)

Conclusion: seed-based CUDA RNG is not a portable candidate identity for these workers.

## Decision

Use a **CPU, NumPy-based, chunk-addressed noise engine** as the one canonical noise source (`numpy_pcg64_normal_f32_to_f16_v1`):

1. Every parameter tensor (from the ParameterSchema) is split into fixed chunks of 262,144 elements.
2. Each chunk has an address `(engine version, candidate seed, schema hash, parameter index, chunk index, chunk size)`. Its seed is the first 128 bits (little-endian) of SHA-256 over that address.
3. Values = `Generator(PCG64(chunk_seed)).standard_normal(n, dtype=float32)`, cast to FP16. These FP16 bytes are the canonical noise.
4. One implementation of this function is used by worker perturbation, coordinator reconstruction, ES update, replay/debug and regression.
5. Engine version, chunk size and the exact NumPy version are recorded in every manifest; the NumPy version is pinned.

The exact byte-level recipe is in numerical-contract.md §4.1. This is the currently selected engineering contract based on evidence — not a claim that it is the only possible solution.

## Alternatives considered

| Alternative | Pros | Cons | Status |
|---|---|---|---|
| **Native CUDA RNG** (`torch.randn_like` on GPU) | Fast, no host→device copy, what the prototype and the audited prior art use | Measured non-portable between our two GPUs, even with matched software | **Rejected by evidence** |
| **Ship full noise tensors** from worker to coordinator | No regeneration needed; trivially consistent | ~1 GB per candidate in FP16 over ordinary networks, every generation; storage on the coordinator | Rejected for routine use; possible as a debug check |
| **PyTorch CPU generator** (`torch.randn` on CPU) | Also GPU-independent; no NumPy dependency | Not probed. The two machines run different PyTorch builds, and we have no evidence about its cross-version stability | Not evaluated |
| **Counter-based RNG** (e.g. Philox) | Random access by counter without per-chunk hashing; could run on GPU | Not probed. A GPU version would reintroduce the cross-architecture risk; the normal transform still needs to be pinned | Candidate for a future version |
| **Own normal transform over raw PCG64 integers** (e.g. Box–Muller) | Removes dependence on NumPy's `Generator` algorithms, which have no version guarantee | Depends on `log`/`cos` being bit-identical across C math libraries, which is not guaranteed | Candidate for v2 if NumPy drift is observed |
| **Shared precomputed noise table** (the approach described in the 2017 OpenAI ES paper) | Deterministic by construction (same file everywhere, checkable by hash); fast slicing | A ~GB table must be distributed and verified; candidates are overlapping slices, so their noise is not independent | Not chosen |

## Consequences

**Positive**

- Noise no longer depends on GPU architecture: full-model bytes were identical on both machines.
- Chunks are independent and order-free, so worker and coordinator may process them in any order or memory budget, and a retry on another worker rebuilds the same candidate.
- Small, auditable implementation (Python `hashlib` + NumPy); golden vectors from the probe can be unit-tested without a GPU or the model.

**Negative / costs**

- **CPU time.** A full-model noise vector took 4.3 s on the 5070 Ti host and 18.1 s on the 1660S host in the probe. That timing includes SHA-256 hashing of the output, so pure generation is somewhat faster. For comparison, one 16-prompt candidate evaluation took 0.7 s and 7.3 s on the respective GPUs. Noise generation can therefore dominate candidate time, especially on the weaker host, and it adds to the coordinator's reconstruction cost (N candidates per generation). This must be measured in the regression and accounted for in C1/C2 timing. Possible mitigations (not yet evaluated): generate chunks in parallel across CPU cores (they are independent), overlap generation with GPU work, or cache ε per candidate on the coordinator (~1 GB each in FP16).
- **Host→device copy** of ~1 GB of FP16 noise per candidate.
- **NumPy stability is a pinned dependency, not a guarantee.** NumPy's own documentation (checked in the 2.5.3 docstrings) states that `PCG64` guarantees a stable integer stream for a fixed seed, but `Generator` — which implements `standard_normal` — has *no* version-compatibility guarantee. Mitigation: pin the exact NumPy version on all machines, record it in manifests, and keep golden-vector tests that fail loudly if the bytes change.
- **Evidence is scoped.** Two x86_64 Linux machines, NumPy 2.5.3 and 2.5.2, Python 3.12 and 3.14. Not a universal cross-platform claim.
- **Probe bytes ≠ production bytes.** The probe's schema hash did not include alias information. If the production schema adds it (numerical-contract.md, decision O1), the production noise for seed 0 differs from the probe's, and portability must be re-proven by the cross-machine same-candidate regression. That regression is already the next gate.

## Evidence

All files in `artifacts/probes/2026-09-29/` (copied unchanged from the original probe directory; see its README for SHA-256 checksums).

| File(s) | Result |
|---|---|
| `probe_5070ti.json`, `probe_1660s.json`, `comparison.json` | CUDA RNG, unmatched runtimes: noise DIFF, candidate predictions DIFF (8/16), restore exact on both |
| `probe_5070ti_matched.json`, `comparison_matched.json` | CUDA RNG, matched torch 2.13/cu132 + Transformers 5.17: same outcome |
| `noiseengine_5070ti.json`, `noiseengine_1660s.json` | NoiseEngine v1 sampled mode: global hash `f9a9baaf…7140` on both |
| `noiseengine_5070ti_full.json`, `noiseengine_1660s_full.json` | NoiseEngine v1 full mode, 290 tensors / 494,032,768 elements / 2,105 chunks: global hash `816c1530…dafda` on both, every chunk hash equal |
| `heteroes_compat_probe.py`, `heteroes_noiseengine_probe.py` | The scripts that produced the above |
