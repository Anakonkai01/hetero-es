# HeteroES-LLM — Numerical Contract

> **Status:** draft v0.1, 2026-09-30 — written by Claude for review, **not yet approved**. Several rules are proposals and are marked as such.
> **Audience:** the project team. Required reading before touching `src/heteroes/{model,noise,es}`.
> **Related:** [architecture.md](architecture.md) (big picture), [ADR-001](adr/ADR-001-canonical-noise-engine.md) (why the NoiseEngine is CPU PCG64). Design source of truth: `HETEROES_LLM_MASTER.md` §6; evidence: `HETEROES_LLM_STATUS.md` §4–5 and `artifacts/probes/2026-09-29/`.

## 0. How to read this document

This document says **exactly** what every machine must compute so that one logical ES candidate is the same candidate everywhere. It is the numerical equivalent of an API contract: worker and coordinator are two independent "implementations" that must agree bit for bit.

Every rule carries a tag:

| Tag | Meaning |
|---|---|
| **[E]** | Backed by physical evidence (probe JSON in `artifacts/probes/2026-09-29/`) |
| **[D]** | Already decided in MASTER / STATUS |
| **[P]** | Proposed by this draft — needs the owner's approval |
| **[OPEN]** | Undecided; options listed in §11 |

"MUST" = violating it makes results invalid. "SHOULD" = strong default; deviations need a written reason.

## 1. Model identity

- **[D]** Model: `Qwen/Qwen2.5-0.5B-Instruct`, revision `7ae557604adf67be50417f59c2c2f167def9a775`. Every model **and tokenizer** load MUST pass `revision=` explicitly.
  - Probes loaded by model id only and read the revision back from `config._commit_hash` **[E]**; the tokenizer revision was recorded as `null` in all three compat probes **[E]**. Production must pin both.
- **[D]** Physical baseline dtype: FP16 on both GPUs.
- **[E]** Facts at that revision: 290 unique parameter tensors, 494,032,768 elements, all floating point.
- Model identity (which weights) is **separate** from schema identity (which layout). A fine-tuned checkpoint keeps the schema but changes the model version.

## 2. ParameterSchema

### 2.1 Purpose

ParameterSchema answers: *which tensors does this model expose for ES, in what canonical order, with what structure?* Its hash is part of every noise address (§4), so two processes that disagree on the layout cannot silently produce "the same" noise for different tensors.

### 2.2 Entry fields [P]

| Field | Type | Meaning |
|---|---|---|
| `index` | int | Position in canonical order, `0 … P-1` |
| `canonical_name` | str | The one name used for this tensor everywhere |
| `aliases` | sorted list[str] | Other names that refer to the same tensor (usually empty) |
| `shape` | list[int] | Tensor shape |
| `dtype` | str | Storage dtype, e.g. `"torch.float16"` |
| `numel` | int | Element count |

Schema document = `{"schema_version": "heteroes.parameter_schema.v1", "entries": [...]}`.

Deliberately **not** in the schema: model id/revision (model identity, §1), weight values, `requires_grad`, device, and any runtime address (`id()`, `data_ptr()`).

### 2.3 Canonical order and alias rule [P]

1. Canonical order = the order of `model.named_parameters()` (default `remove_duplicate=True`), i.e. module registration order. **[E]** For Qwen this is exactly the 290-entry order used by both probes (index 0 = `model.embed_tokens.weight`, index 289 = `model.norm.weight`).
2. Alias discovery = walk `model.named_parameters(remove_duplicate=False)` and group names by `id(param)` **inside the current process only**. A group has aliases when `len(names) > 1` (the notebook's `> 2` was a bug **[E]**).
3. `canonical_name` = the name that step 1 yields for that tensor (its first occurrence); `aliases` = the remaining names, sorted.
4. **[E]** Qwen: exactly one alias group, `["lm_head.weight", "model.embed_tokens.weight"]` → entry 0 has `canonical_name = "model.embed_tokens.weight"`, `aliases = ["lm_head.weight"]`. This tensor is 136,134,656 elements (~28% of the model).
5. Every parameter MUST be floating point; otherwise building the schema fails.

A tied tensor is **one** entry: perturbed once, restored once, updated once.

### 2.4 Hash [D — O1 decided 2026-10-01: option (a)]

`schema_hash = SHA-256( canonical_json(schema_document) )` where `canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")` — the same serialization the probes used.

> **Decided (O1 = a):** the production schema hash includes `aliases` and `schema_version`. The probe hash `152e9d82…88e1` (which had no alias information) will **not** equal the production hash, and therefore the production noise bytes for seed 0 will differ from the probe's bytes (the schema hash is part of the noise address). Consequences: (1) the golden vectors in §4.4 belong to the **probe** schema hash and remain valid only as evidence for the generation recipe; production golden vectors must be regenerated from the production hash; (2) the cross-machine regression (§9) must be re-run with the production hash. See decision O1 in §11.

### 2.5 API sketch [P] — design only, no code yet

| Function | Input → Output | Notes |
|---|---|---|
| `build_parameter_schema(model)` | model → `ParameterSchema` | Pure w.r.t. layout; no weights read |
| `ParameterSchema.hash` | → hex str | §2.4 |
| `ParameterSchema.to_json()` / `from_json()` | ↔ str | For manifests; round-trip must preserve the hash |
| `verify_model_matches(model, schema)` | → None or raises `SchemaMismatchError` | Called by worker and coordinator before any perturb/update |
| `resolve_tensors(model, schema)` | → list of live tensors by `index` | In-process only; never serialized |

### 2.6 Tests to write [P]

| # | Test | Guards against |
|---|---|---|
| S1 | Build twice → same hash | Non-determinism |
| S2 | Toy model with two names on one `nn.Parameter` → one entry, `aliases=[second name]` | Double perturbation of tied weights |
| S3 | Toy model with exactly two aliases is detected | The historical `len(names) > 2` bug |
| S4 | Two *different* tensors with the same shape → two entries | Over-eager aliasing |
| S5 | Changing shape / dtype / order / alias set changes the hash | Weak hash |
| S6 | Serialized keys are exactly the fields in §2.2 | Runtime addresses leaking into identity |
| S7 | Integer parameter → error | Silent skipping |
| S8 | `verify_model_matches` raises on a modified model | Silent mismatch |
| S9 (slow, needs model) | Qwen at pinned revision → 290 entries, 494,032,768 elements, one alias group with the names above | Regression vs probe evidence |

## 3. Candidate seed namespace [OPEN]

The noise engine takes an integer `candidate_seed`. How seeds are chosen is not decided yet (decision O5).

- Observation **[E]**: the notebook reused seeds `[0, 1, 2, 3]` every generation. `milestone2_history.json` shows three generations with identical rewards, z-scores and `update_max_diff = 0.00030517578125`: with the same seeds and a model whose predictions did not change, every generation applied the **same** update direction again. That is acceptable for a frozen regression benchmark but not as a training policy.
- Whatever rule is chosen, the seed MUST be recorded in the candidate descriptor/manifest, and MUST NOT depend on worker, attempt, lease or retry.

## 4. CanonicalNoiseEngine v1

### 4.1 Definition [D][E]

Engine version string: `numpy_pcg64_normal_f32_to_f16_v1`. Chunk size: `chunk_elements = 262144` (2^18).

For a noise **address** `(candidate_seed, schema_hash, parameter_index, chunk_index, chunk_elements)`:

```text
material = UTF-8 bytes of
  "numpy_pcg64_normal_f32_to_f16_v1|candidate_seed={seed}|schema={schema_hash}|param={parameter_index}|chunk={chunk_index}|chunk_elements={chunk_elements}"
  (integers in base-10 ASCII, schema_hash as lowercase hex)

chunk_seed = int.from_bytes(SHA-256(material)[0:16], byteorder="little", signed=False)

rng    = numpy.random.Generator(numpy.random.PCG64(chunk_seed))
values = rng.standard_normal(n, dtype=numpy.float32)      # generation dtype
noise  = values.astype(numpy.float16)                      # canonical bytes, little-endian
```

This is byte-for-byte the recipe of `heteroes_noiseengine_probe.py` **[E]**. The production module MUST reproduce it exactly; a string-format change is an engine version change.

### 4.2 Chunk layout [P — implied by the probe, stated explicitly here]

- A parameter is viewed as a flat array in row-major (C) order of its `numel` elements.
- Chunk `j` covers elements `[j·C, min((j+1)·C, numel))`, with `C = chunk_elements`; `n` is that length. The last chunk may be shorter (e.g. embedding chunk 519 has 81,920 elements) and takes the **first** `n` values of its own stream.
- Chunks per parameter = `ceil(numel / C)`; the whole Qwen model has 2,105 chunks **[E]**.

### 4.3 Invariants

| # | Invariant | Status |
|---|---|---|
| N1 | Same address → identical bytes on every supported machine | **[E]** full model, both machines, NumPy 2.5.3 vs 2.5.2 |
| N2 | Bytes of a chunk do not depend on which other chunks were generated, or in which order | By construction (independent seed per chunk) |
| N3 | Operational metadata (worker, attempt, lease, retry, reward, workload, time) is never part of the address | **[D]** |
| N4 | One implementation serves worker perturbation, coordinator reconstruction, ES update, replay/debug and regression | **[D]** |
| N5 | Engine version, chunk size and exact NumPy version are recorded in every manifest | **[D]** |

### 4.4 Golden vectors [E]

From the full probe (candidate_seed 0, **probe** schema hash `152e9d82e61d6610a414466026ac60a13e718924dfdf0416809686adcf4188e1`, C = 262144). Identical on both machines; SHA-256 of the FP16 chunk bytes:

| param | name | chunk | n | SHA-256 of chunk bytes |
|---|---|---|---|---|
| 0 | model.embed_tokens.weight | 0 | 262144 | `1c7a5a141fb785001881807b2bf0c9f81a1f2acf61877b1d2b2e4d029cfb8a35` |
| 0 | model.embed_tokens.weight | 519 | 81920 | `8f57f603def436e1a642e71988b80a39331efaf9273e32634fe9f305f48ec405` |
| 1 | model.layers.0.self_attn.q_proj.weight | 0 | 262144 | `34cc1872a32730731bb5b753277885281dd31aa0c27fdfbdcdd09c001a23eda8` |
| 2 | model.layers.0.self_attn.q_proj.bias | 0 | 896 | `56d3f8f512beadbebf9cbf0b1e6fda5143f7940375fc4af99a3437943af12602` |
| 289 | model.norm.weight | 0 | 896 | `3ed137fd746d5f0655e81731e39e80df6857404c5644dad5dd40b6a6767a25ae` |

Because the engine takes `schema_hash` as a plain string input, these vectors can be unit-tested **without loading the model**, and they tie the production engine directly to the physical evidence. Proposed test: the engine, given the probe schema hash string, must reproduce every row above. A NumPy upgrade that changes `standard_normal` then fails loudly in CI instead of silently changing candidates (see ADR-001 on NumPy's compatibility policy).

### 4.5 Tests to write [P]

| # | Test |
|---|---|
| N-G | Golden vectors of §4.4 reproduced exactly |
| N-O | Generating chunks in shuffled order gives the same bytes per chunk |
| N-D | Different seed / param index / chunk index / chunk size / schema hash / engine version → different bytes |
| N-L | Last-chunk length and total chunk count follow §4.2 |
| N-M | Address type rejects extra fields (no worker/attempt ids can be passed in) |

## 5. Perturbation

- **[D]** Perturbed weights = θ + σ·ε, stored in the model dtype (FP16).
- **[D]** σ is part of the **candidate**, not of the noise. Proposed **[P]**: record σ in manifests together with its exact float32 value, since `1e-3` is not exactly representable in binary floating point.
- **[OPEN] How the arithmetic is performed** (decision O2). This matters because the cross-machine gate compares hashes of perturbed weights, so the formula itself must be deterministic across GPUs:
  - (a) notebook style on GPU: `param.add_(eps, alpha=sigma)` in FP16;
  - (b) on CPU: `fp16( fp32(θ) + fp32(σ) · fp32(ε) )` with NumPy, then copy to GPU;
  - (c) on GPU with explicit separate operations in FP32: `t = ε.float() * σ`, then `(θ.float() + t).half()`.
  - *Inference, not yet verified:* single IEEE-754 multiplications and additions are correctly rounded, so (b) and (c) should be bit-identical across machines if no operation is fused. Option (a) leaves the internal precision and possible fusion to the kernel. The cross-machine regression is the test that settles it.
- Every parameter entry is perturbed exactly once (tied tensors once, §2.3).

## 6. Restore

- **[D][E]** Canonical restore = copy θ back from a full snapshot, then verify. Arithmetic undo (`−σ·ε`) is never a correctness oracle.
- **[E]** Probes: CPU snapshot (~0.3 s on the 5070 Ti, ~0.8 s on the 1660S), restore + verify 0.07 s / 0.28 s, max diff 0.0 on both.
- **[P] Use a bitwise oracle.** The current checks use `(param − source).abs().max()`. That check is blind to NaN (a NaN difference never beats `max_diff`, so a NaN-corrupted tensor can report `0.0`) and to `+0.0` vs `−0.0`. Proposed: compare the raw bits per tensor (e.g. compare the FP16 tensors reinterpreted as int16), which is exact and NaN-safe.
- **[D]** Verification MUST be memory-safe on the 6 GB 1660S: per tensor, and per chunk for the embedding tensor if needed — without weakening the oracle.
- A restore failure MUST mark the worker unusable for further candidates (quarantine, C3).

## 7. Reward standardization

- **[D][E]** Rewards MUST be finite; NaN/Inf → reject the generation input, never coerce to 0. Infrastructure failures are not rewards.
- **[E]** Notebook formula: `μ = mean(R)`, `s = std(R, population)`; if `s < η` → all `z = 0` (no-op update, logged); else `z = (R − μ) / (s + η)`, with `η = 1e-8`.
- **[P]** Record `η` in the config. Note it is used twice: as the "equal rewards" threshold and as the division guard.

## 8. ES update

- **[D]** Method A (parameter-outer), MASTER §24.7:

```text
for each schema entry k (canonical order):
    direction = zeros(numel_k, FP32)
    for i in candidate canonical order:            # NOT result arrival order
        direction += z_i · fp32(ε_i,k)             # ε from the same NoiseEngine
    direction /= N
    θ_k ← fp16( fp32(θ_k) + α · direction )        # cast once
```

- **[D]** Accumulation MUST be FP32. **[E]** The notebook accumulates in FP16 (`torch.zeros_like(param)` on an FP16 model); this is known debt.
- **[P]** `ε_i` in the update is the canonical FP16 noise upcast to FP32 — the same bytes the worker used. (The realized perturbation `fp16(θ + σε) − θ` differs slightly from `σε` because of rounding; the update uses the canonical ε, not the realized difference.)
- **[D]** Candidate order is canonical because floating-point addition is not associative: summing in arrival order would make the update depend on network timing.
- **[D]** Diagnostics: requested update norm, actually applied update (after the FP16 cast), fraction of coordinates that changed, tied-tensor behaviour. **[E]** `milestone2_history.json` reports `update_max_diff = 0.00030517578125` with the worst parameter `model.embed_tokens.weight`.
- Memory note: the largest FP32 `direction` (embedding) is 136,134,656 × 4 B ≈ 545 MB.

## 9. Cross-machine same-candidate regression (the gate)

For one candidate (same revision, schema, seed, σ, workload) on the 5070 Ti and the 1660S:

| Check | Required |
|---|---|
| Noise hash per parameter (all 290 entries) | Equal |
| Perturbed-weight hashes (sampled, declared up front) | Equal |
| Restore bitwise-exact on each machine | PASS on both |
| All 16 predictions recorded on both | Required |
| Reward recorded on both | Required |
| Any prediction difference | Measured and explained, never hidden behind an equal reward |
| Perturb and reconstruct use the same code path | Required |

**[E]** Why reward alone is not enough: in the CUDA-RNG probe both machines scored candidate reward 0.25 while 8 of 16 candidate predictions differed. **[E]** Encouraging sign: *base* predictions (unperturbed weights) matched on both GPUs, so identical weights may well give identical greedy outputs — but that must be measured for perturbed weights, not assumed.

## 10. Reproducibility limits

- Evidence covers two x86_64 Linux machines (same kernel/glibc), NumPy 2.5.3 and 2.5.2, one model revision. It is **not** a universal guarantee.
- **NumPy policy (verified in the NumPy 2.5.3 docstrings):** `PCG64` guarantees that a fixed seed always produces the same integer stream; `Generator` — which provides `standard_normal` — has **no** version-compatibility guarantee ("as better algorithms evolve the bit stream may change"). The exact NumPy version MUST be pinned and recorded; the golden-vector test (§4.4) detects drift.
- The `ai` environment has NumPy 2.4.5, which has never been tested against the golden vectors. Do not use it for canonical noise until it passes them.
- Canonical bytes assume little-endian storage (true for both machines).
- Even with identical weights, GPU inference may produce different outputs on different architectures; this is measured separately (§9).

## 11. Decisions needed from the owner

| # | Question | Options | Draft recommendation |
|---|---|---|---|
| O1 | Schema hash for production | (a) include aliases + `schema_version` (hash changes from the probe); (b) keep the probe-compatible hash and validate aliases separately | **DECIDED 2026-10-01: (a)** — MASTER requires aliases in schema identity; portability is re-proven at the gate anyway |
| O2 | Perturbation arithmetic | (a) GPU FP16 `add_`; (b) CPU FP32 then cast; (c) GPU explicit FP32 separate ops then cast | (c), verified by the gate; fall back to (b) if hashes differ |
| O3 | Restore oracle | abs-max diff (current) vs bitwise | Bitwise |
| O4 | ε used in the update | canonical FP16 ε upcast to FP32 vs realized difference | Canonical ε |
| O5 | Candidate seed rule | (a) explicit seed list stored in the manifest; (b) derive from (experiment, generation, candidate index) | Decide at manifest freeze (step 8); keep fixed `[0..3]` for the frozen regression |
| O6 | NumPy pin | exact version on both machines (which one?) | Pin one exact version (2.5.3 was probed on the 5070 Ti) on both machines, and confirm Python 3.14 on the 1660S has a wheel for it |

## Appendix A — Known deviations of the probes/notebook from this contract

| Where | Deviation | Contract section |
|---|---|---|
| Both probes, notebook | Model loaded without `revision=`; tokenizer revision not recorded | §1 |
| Both probes | Schema without alias information | §2.4 |
| Notebook `find_parameter_aliases` | `len(names) > 2` misses two-name groups | §2.3 |
| Notebook `restore_canonical_parameters` | Shape-mismatch error message references undefined `source` | §6 |
| Probes, notebook `full_parameter_max_diff` | abs-max diff oracle (NaN-blind); notebook version also mis-reports the worst parameter when diffs tie | §6 |
| Notebook `es_update_direction` | FP16 direction accumulation | §8 |
| Notebook perturb / reconstruct / update | CUDA `torch.Generator` noise, duplicated in several functions | §4 |
| Notebook `run_es_generation` | Reward-after measured on the same 16 training prompts (no held-out set) | out of scope here |
