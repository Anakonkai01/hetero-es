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

> **Implementation status (2026-10-02; S9 also passed on the 1660S on 2026-10-03):** `find_alias_groups`, `SchemaEntry`, `ParameterSchema` (`to_dict`, `hash`) and `build_parameter_schema` exist in `src/heteroes/model/schema.py`, with tests in `tests/model/test_schema.py` (covers S1–S6, S9). Not implemented yet: `to_json` / `from_json`, `verify_model_matches`, `resolve_tensors`, `SchemaEntry.__post_init__` validation (S7 is covered only by the non-floating check in `build_parameter_schema`; S8 not covered). Measured on the Qwen2.5-0.5B layout: 290 entries, 494,032,768 elements, one alias group; hashing the entries in the probe's format reproduces the probe hash `152e9d82…88e1`; production hash (aliases + `schema_version`) is `0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec`.

### 2.5 API sketch [P] — partly implemented, see status note above

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

These are the **probe** vectors (probe schema hash). Production-schema-hash vectors for the same five chunks are in `tests/noise/test_engine.py` (`GOLDEN_PRODUCTION`); they were produced by this engine and then reproduced independently by the standalone script on the 1660S, Colab and Kaggle, so they are cross-machine evidence for the production hash too (see the comment above that table).

Because the engine takes `schema_hash` as a plain string input, these vectors can be unit-tested **without loading the model**, and they tie the production engine directly to the physical evidence. Implemented as tests N-G in `tests/noise/test_engine.py`. Original proposal: the engine, given the probe schema hash string, must reproduce every row above. A NumPy upgrade that changes `standard_normal` then fails loudly in CI instead of silently changing candidates (see ADR-001 on NumPy's compatibility policy).

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
- **[D — O2 decided 2026-10-03: option (c)] How the arithmetic is performed.** The formula must give the same bits on every machine, because the cross-machine gate compares hashes of perturbed weights. Candidates:
  - (a) notebook style on GPU: `param.add_(eps, alpha=sigma)` in FP16;
  - (b) on CPU: `fp16( fp32(θ) + fp32(σ) · fp32(ε) )` with NumPy, then copy to GPU;
  - (c) **chosen**: on GPU with explicit separate operations in FP32: `t = ε.float() * σ`, then `(θ.float() + t).half()`. Each step MUST be its own operation (see the fusion warning below).
  - **Evidence [E]** (`artifacts/regression/2026-10-03-o2-perturbation/`, script `scripts/o2_cross_gpu_check.py`, commit `7b73e03`): all 494,032,768 weights of Qwen2.5-0.5B at the pinned revision, noise from this engine (production schema hash, seed 0, σ = float32(1e-3)). The whole-model hash of the perturbed weights is identical (`8aa3eb9af895cb4a…`) for (c) on GPU, (b) on CPU (NumPy), torch on CPU, whole tensor or per chunk, and across four environments: RTX 5070 Ti (Blackwell, torch 2.10 and 2.13), Tesla T4 on Colab and on Kaggle (Turing, torch 2.11), GTX 1660 SUPER (Turing, torch 2.13); NumPy 2.1.3, 2.4.5, 2.5.2, 2.5.3; Python 3.12 to 3.14.
  - **Option (a) is also a viable candidate, kept as a noted alternative [E].** `add_(alpha)` gave the same whole-model hash (`ce33fa32…`) in all four environments too, and it equals an emulated single-rounding FMA (fp32). It differs from (c) in 167 of 494,032,768 elements (σ = 1e-3, base model; 91 of them only in the sign of zero, max 1 ULP). It was not chosen because (i) it relies on PyTorch's kernel fusing the multiply and the add, an implementation detail, and (ii) `add_(alpha)` on the CPU gives a different result from `add_(alpha)` on the GPU in 9.6% to 9.9% of the elements (47.3 to 48.8 million, depending on the machine), so a CPU reconstruction could not use it. If (a) is ever preferred, the whole contract (worker, coordinator, tests) must switch to it together.
  - **Not portable [E], do not use:** all-FP16 steps on the GPU (`t + e*sigma`) gave two different whole-model hashes across the four environments (T4 differs from the other two environments, although the 1660S has the same architecture as the T4, so the architecture alone does not explain it; cause unknown); `add_(alpha)` on the CPU in FP16 gave three different hashes on three CPUs (cause unknown).
  - **Fusion warning [inference, not verified]:** CUDA compilers may contract `a*b + c` into one FMA when both operations are inside the same kernel. (c) is only safe while the multiplication and the addition stay separate PyTorch operations (eager mode). A hand-written fused kernel or `torch.compile` could change the bits and must be re-verified with the script above.
  - **Limits:** one seed (0); one σ (1e-3) in the four-environment comparison (σ = 0.01 was run on the 5070 Ti only, with the same class structure but more elements differing between (a) and (c)); all four environments are x86_64 Linux; the compute method was exercised by a script, the repo has no perturb function yet.
- Every parameter entry is perturbed exactly once (tied tensors once, §2.3).

> **Implementation status (2026-10-05):** `perturb_parameter_` and `perturb_model_` in `src/heteroes/es/perturb.py`. On the real model (original checkpoint, seed 0, sigma = float32(1e-3), production schema hash) the package reproduces the whole-model hash `8aa3eb9af895cb4a…` of the four environments, on the 5070 Ti GPU and with the GPU hidden (CPU only). Not run on the 1660S yet. All checks (schema, dtype, contiguity, sigma) happen before the first write; a failure while writing (for example out of memory) still leaves the model half perturbed, which is what restore (§6) is for.

## 6. Restore

- **[D][E]** Canonical restore = copy θ back from a full snapshot, then verify. Arithmetic undo (`−σ·ε`) is never a correctness oracle.
- **[E]** Probes: CPU snapshot (~0.3 s on the 5070 Ti, ~0.8 s on the 1660S), restore + verify 0.07 s / 0.28 s, max diff 0.0 on both.
- **[D — O3 decided 2026-10-01] Use a bitwise oracle.** The current checks use `(param − source).abs().max()`. That check is blind to NaN (a NaN difference never beats `max_diff`, so a NaN-corrupted tensor can report `0.0`) and to `+0.0` vs `−0.0`. Decided: pass/fail is determined by comparing the raw bits per tensor (e.g. compare the FP16 tensors reinterpreted as int16), which is exact and NaN-safe. An abs-max difference MAY additionally be reported as a diagnostic when the bitwise check fails, but it never decides pass/fail.
- **[D]** Verification MUST be memory-safe on the 6 GB 1660S: per tensor, and per chunk for the embedding tensor if needed — without weakening the oracle.
- A restore failure MUST mark the worker unusable for further candidates (quarantine, C3).

> **Implementation status (2026-10-05):** `take_snapshot`, `diff_from_snapshot`, `restore_from_snapshot_` and `RestoreError` in `src/heteroes/es/snapshot.py`. The snapshot is a CPU copy; the oracle compares raw bits through an int16 view, slab by slab (default 2^24 elements), so NaN and the sign of zero cannot hide a difference and no full-size temporary is created on the device. On the real model, perturb followed by restore gives back identical weights (SHA-256 equal) with less than 256 MiB of extra GPU memory (bound asserted; the actual peak was not recorded). Not run on the 1660S yet. A slab size below 1 is rejected, because an empty range would make the oracle answer "identical".

## 7. Reward standardization

- **[D][E]** Rewards MUST be finite; NaN/Inf → reject the generation input, never coerce to 0. Infrastructure failures are not rewards.
- **[E]** Notebook formula: `μ = mean(R)`, `s = std(R, population)`; if `s < η` → all `z = 0` (no-op update, logged); else `z = (R − μ) / (s + η)`, with `η = 1e-8`.
- **[P]** Record `η` in the config. Note it is used twice: as the "equal rewards" threshold and as the division guard.
- **[P]** Implementation (`src/heteroes/es/update.py`, tests `tests/es/test_standardize.py`): the input is any 1-D sequence of real numbers (list, tuple, NumPy array; ints allowed). It is converted to float64 first, the mean and the population standard deviation (`ddof = 0`) are computed in float64, and the coefficients are rounded **once** to float32. The returned float32 array is the exact set of coefficients every machine uses. Record `ddof = 0` and `η` next to the coefficients in the manifest.

### 7.1 How other ES code handles rewards (looked up 2026-10-05)

Purpose: to see which choices of this contract are common practice and which are deliberate differences.

**How reliable this is.** The code of the four projects below was read through a page summarizer (WebFetch), **not checked word for word against the raw files**. The EGGROLL paper was read directly from the PDF text. `es-at-scale` was read at `main`, while STATUS audited commit `574a9d1`; they may differ. Re-open the exact file before quoting any line in the report.

| | es-at-scale | understanding-es | Agentic-ESOpt | EGGROLL (HyperscaleES) |
|---|---|---|---|---|
| Formula | `(r - mean) / (std + 1e-8)` | `(r - mean) / (std + eps)` | z-score `(r - mean) / (std + eps)`, eps default `1e-8`; also `centered_rank`, or off | `(r - mean) / sqrt(var + 1e-5)` |
| ddof | NumPy default (0) | parameter `ddof` | parameter `ddof` | `jnp.var` default (0) |
| Reward dtype | Python float, stats in NumPy float64 | `np.float64` array | `torch.float32` | not seen in the parts read |
| NaN / Inf | not checked; a timeout becomes `0.0` | not checked (a missing candidate raises `RuntimeError`) | checked, `ValueError` | not seen |
| Equal rewards | no special case | no special case | returns zeros when `n <= ddof` | not seen |
| Update accumulation | FP32; noise generated in the model dtype, then `.to(float32)`; cast to the model dtype once | FP32; noise generated directly in FP32 | FP32; cast once | cast to `param.dtype` at the end |
| Adding one candidate | `term = noise.float() * coeff; acc.add_(term)` | `total_delta.add_(noise, alpha=scale*weight)` | same as understanding-es | not read |
| Candidate order | order of the seed list | sequential `zip(seeds, weights, strict=True)` | sequential | not read |

EGGROLL is different in kind (read directly from the paper): Algorithm 1 and Eq. (6) use the **raw** fitness, `M <- M + (alpha/N) * sum_i E_i * f(M + sigma*E_i)`, with `1/sigma` absorbed into the learning rate. For the LLM experiments it normalizes the score **per question** with a global variance and averages over the questions (the paper compares this to the group relative advantage of GRPO). For the int8 model (appendix H.2) the coefficient is `sign(s+ - s-)` of an antithetic pair, so only `{-1, 0, 1}` is possible. The `HyperscaleES` code (through the summarizer) puts `1e-5` **inside** the square root of the variance and multiplies the update by `sqrt(N)`.

**Measured (2026-10-05, scratch script, not in the repo).** The common formula `(r - mean) / (std + 1e-8)` applied to 20,000 random cases in which *all rewards are identical*: in float64 some coefficients are not zero in 6,269 cases, but the largest `|z|` is 4.4e-8 (harmless); in float32 some coefficients are not zero in 8,898 cases and the largest `|z|` is 0.96 (a false signal). Cause: the mean of identical numbers can be off by one rounding unit, and dividing by `std + eps` with `std = 0` turns that into a coefficient of order 1 in float32. This is a test of the *formula*, not a run of those projects' code; whether their code is exposed depends on their reward values (rewards that are exact in binary, such as `k/16`, are not affected). It is the reason this contract computes the statistics in float64 and uses an explicit threshold `s < eta` that returns all zeros.

**What follows for this contract**

- Common practice, same as here: z-score with `eta = 1e-8`, population standard deviation, FP32 accumulation, one cast to the model dtype at the end. `es-at-scale` also generates the noise in the model dtype and upcasts it to FP32, which is what option O4 proposes (section 8).
- Deliberate differences:
  1. Non-finite rewards are rejected. Only Agentic-ESOpt checks; `es-at-scale` turns a timeout into `0.0`, which MASTER already says not to copy.
  2. An explicit `s < eta` rule instead of relying on the epsilon (see the measurement above).
  3. The multiply and the add are separate operations. All three projects use the fused `add_(..., alpha=...)`; they do not need the same bits on different machines, this project does (same lesson as O2 in section 5).
  4. Placement of `alpha/N`: they fold it into the coefficient of each candidate; section 8 accumulates `sum z_i * eps_i` first, then divides by `N`, then multiplies by `alpha`. The mathematics is the same, the rounding is not. This is a contract choice, not a defect of either.
- Not adopted here, kept as future options: per-question normalization and antithetic sign shaping (EGGROLL), rank transform (Agentic-ESOpt). MASTER says not to change the recipe silently.

Sources: EGGROLL paper https://arxiv.org/pdf/2511.16652 and page https://eshyperscale.github.io/ ; code https://github.com/ESHyperscale/HyperscaleES , https://github.com/VsonicV/es-at-scale , https://github.com/yunpengba7/understanding-es , https://github.com/zz1358m/Agentic-ESOpt .

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
- Memory note: the largest FP32 `direction` (embedding) is 136,134,656 × 4 B ≈ 545 MB if built for the whole tensor. Every operation is elementwise and the candidate loop is the innermost one, so accumulating one chunk at a time gives the same bits and needs only about one chunk (1 MiB) of FP32 memory.

> **Implementation status (2026-10-05): NOT finished.** The specification tests exist (`tests/es/test_standardize.py`, `tests/es/test_update.py`; independent NumPy oracle, FP32-versus-FP16 and candidate-order cases chosen so that the data can tell them apart: on 200,000 elements and 8 candidates, FP16 accumulation differed in 111,076 elements and a different candidate order in 41). `src/heteroes/es/update.py` is an unfinished draft. Decisions proposed but not approved: O4 (canonical epsilon), rejecting duplicate seeds, the report fields (`noop`, `coefficients`, `requested_l2`, `applied_l2`, `changed`, `numel`).

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

- Evidence covers four x86_64 Linux environments (RTX 5070 Ti, GTX 1660 SUPER, Colab T4, Kaggle T4), NumPy 2.1.3, 2.4.5, 2.5.2 and 2.5.3, Python 3.12 to 3.14, one model revision (full-model noise hash and perturbed-weight hash identical in all four; `artifacts/regression/2026-10-03-o2-perturbation/`). The original 29/09 probe covered the two physical machines only. It is **not** a universal guarantee (no ARM, no other OS, one seed, one σ for perturbation).
- **NumPy policy (verified in the NumPy 2.5.3 docstrings):** `PCG64` guarantees that a fixed seed always produces the same integer stream; `Generator` — which provides `standard_normal` — has **no** version-compatibility guarantee ("as better algorithms evolve the bit stream may change"). The exact NumPy version MUST be pinned and recorded; the golden-vector test (§4.4) detects drift.
- The `ai` environment has NumPy 2.4.5. On 2026-10-02 the five golden vectors of §4.4 were reproduced under it (scratch script). On 2026-10-03 the full-model noise hash (2,105 chunks) was reproduced under 2.4.5 (5070 Ti) and 2.1.3 (Colab, Kaggle) by `scripts/o2_cross_gpu_check.py`, in addition to 2.5.2 and 2.5.3 from the 29/09 probe. **O6 (which single version to pin) is still open**; `pyproject.toml` does not pin NumPy yet.
- Canonical bytes assume little-endian storage (true for both machines).
- Even with identical weights, GPU inference may produce different outputs on different architectures; this is measured separately (§9).

## 11. Decisions needed from the owner

| # | Question | Options | Draft recommendation |
|---|---|---|---|
| O1 | Schema hash for production | (a) include aliases + `schema_version` (hash changes from the probe); (b) keep the probe-compatible hash and validate aliases separately | **DECIDED 2026-10-01: (a)** — MASTER requires aliases in schema identity; portability is re-proven at the gate anyway |
| O2 | Perturbation arithmetic | (a) GPU FP16 `add_`; (b) CPU FP32 then cast; (c) GPU explicit FP32 separate ops then cast | **DECIDED 2026-10-03: (c)**, evidence in §5 (bit-identical on 4 environments incl. the 1660S). (a) kept as a noted alternative (also identical across the 4 environments) |
| O3 | Restore oracle | abs-max diff (current) vs bitwise | **DECIDED 2026-10-01: bitwise** (abs-max only as optional diagnostic) |
| O4 | ε used in the update | canonical FP16 ε upcast to FP32 vs realized difference | Canonical ε (proposed; the step-5 tests assume it; not yet formally approved) |
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
