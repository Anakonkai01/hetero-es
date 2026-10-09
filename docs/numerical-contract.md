# HeteroES-LLM — Numerical Contract

> **Status:** draft v0.1, 2026-09-30 — written by Claude for review, **not yet approved**. Several rules are proposals and are marked as such.
> **Audience:** the project team. Required reading before touching `src/heteroes/{model,noise,es}`, `generation_record.py` and `ledger/`.
> **Updated 2026-10-06:** the update can be applied from given coefficients (section 8), a question of who computes them was decided (O7, section 11), and the record of a generation is section 13.
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

## 3. Candidate seed namespace [D — O5 decided 2026-10-06]

The noise engine takes an integer `candidate_seed`. Decision O5 (2026-10-06): **seeds are explicit data**, written in every candidate descriptor (section 12); the coordinator chooses them, the workers never derive them.

- Observation **[E]**: the notebook reused seeds `[0, 1, 2, 3]` every generation. `milestone2_history.json` shows three generations with identical rewards, z-scores and `update_max_diff = 0.00030517578125`: with the same seeds and a model whose predictions did not change, every generation applied the **same** update direction again. That is acceptable for a frozen regression benchmark but not as a training policy.
- Whatever rule is chosen, the seed MUST be recorded in the candidate descriptor/manifest, and MUST NOT depend on worker, attempt, lease or retry.
- **[D — decided 2026-10-05] What one ES update accepts.** The seeds of one update MUST be real integers (`int` or a NumPy integer; `bool`, `float`, `str`, `None` raise `TypeError`) and pairwise distinct (a duplicate raises `ValueError`); both checks happen before the first write. Reason [E, checked 2026-10-05]: the engine writes the seed into the address text, so `1`, `np.int64(1)` and `"1"` give the same noise, while `1.0` and `True` give different noise; a duplicate check on raw values (for example with a `set`) would therefore be wrong in both directions. Two candidates with the same seed have the same ε: that direction would be counted twice, the reward statistics would not describe independent samples, and it could hide a retry that was counted twice (C3).
- **[D — O5 decided 2026-10-06]** Seeds are explicit: every candidate descriptor carries its seed, so a worker never needs a rule to know it. The noise address does not contain the generation, so reusing a seed in the next generation gives the same ε again; the update function does not check this. The frozen regression keeps the fixed list `[0..3]` (the 2026-10-05 and 2026-10-06 evidence used seed 0). For real runs the coordinator SHOULD use `heteroes.manifest.derive_seed(experiment_id, generation, index)`: 52 bits of SHA-256 of `heteroes-seed-v1|experiment|generation|index`, repeatable, different for every generation. That function is a way of CHOOSING seeds, not part of the contract between machines (it is not in the recipe hash). Measured 2026-10-06: 128,000 derived seeds (2000 generations of 64) were all distinct, the largest was below 2^52.
- **[D — decided 2026-10-06] Seed range.** In a descriptor a seed is a plain integer with `0 <= seed < 2^53`, because JSON read by JavaScript (the product layer) keeps integers exactly only below 2^53. The engine itself still accepts any integer (so the golden vectors do not change); the limit is a rule of the manifest, not of the noise.

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
- **[E]** Notebook formula: `μ = mean(R)`, `s = std(R, population)`; if `s < η` → all `z = 0` (no-op update, logged); else `z = (R − μ) / (s + η)`, with `η = 1e-9` (**[D]** decided by the owner 2026-10-05; the notebook used `1e-8`).
- **[P]** Record `η` in the config. Note it is used twice: as the "equal rewards" threshold and as the division guard.
- **[P]** Implementation (`src/heteroes/es/update.py`, tests `tests/es/test_standardize.py`): the input is any 1-D sequence of real numbers (list, tuple, NumPy array; ints allowed). It is converted to float64 first, the mean and the population standard deviation (`ddof = 0`) are computed in float64, and the coefficients are rounded **once** to float32. The returned float32 array is the exact set of coefficients every machine uses. Record `ddof = 0` and `η` next to the coefficients in the manifest.
- **[D — O7, 2026-10-06] The coefficients are computed ONCE, by the coordinator, and then travel (section 13); no other machine recomputes them from the rewards.** [E] Reason: when a reward equals the mean, its coefficient is `0.0` or a residue of about 1e-16 depending on the order of the float64 sums. With rewards k/96 another order of the sums changed the float32 coefficients in 0.3 to 0.4% of 20,000 random sets (N = 8, 16, 64), every time of this kind and only this kind; a synthetic 2-million-element update did not change any FP16 weight (`artifacts/experiments/2026-10-06-coefficient-residue/`). The weights are practically unaffected, but the bytes of the coefficient vector are not, so recomputing and comparing would raise a false alarm in about 1 generation in 300.

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

- Common practice, same as here: z-score, population standard deviation, FP32 accumulation, one cast to the model dtype at the end. `es-at-scale` also generates the noise in the model dtype and upcasts it to FP32, which is what option O4 proposes (section 8).
- Deliberate differences:
  1. Non-finite rewards are rejected. Only Agentic-ESOpt checks; `es-at-scale` turns a timeout into `0.0`, which MASTER already says not to copy.
  2. An explicit `s < eta` rule instead of relying on the epsilon (see the measurement above).
  2b. `eta = 1e-9` (owner's decision, 2026-10-05) where the projects above use `1e-8`. The measurement above was made with `1e-8`; it was not repeated with `1e-9`.
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
- **[D — O4 decided 2026-10-05: option A]** `ε_i` in the update is the canonical FP16 noise upcast to FP32 — the same bytes the worker used. (The realized perturbation `fp16(θ + σε) − θ` differs slightly from `σε` because of rounding; the update uses the canonical ε, not the realized difference.)
  - **Two roundings sit between the ideal noise and the realized perturbation** (cast of ε to FP16 in the engine; storing θ' in FP16 in perturb). The FP16 → FP32 upcast itself adds no error.
  - **Measured 2026-10-05 [E]** (scratch scripts, not in the repo; Qwen2.5-0.5B at the pinned revision, all 494,032,768 elements, seeds 0 to 3, σ = float32(1e-3), NumPy 2.4.5, original unmodified weights, CPU): (i) cast of ε to FP16: ‖ε₁₆ − ε₃₂‖ / ‖ε₃₂‖ = 2.08e-4; mean ≈ 0, variance 1.0000, kurtosis ≈ 3.000, no value flushed to 0; the update direction Σ zᵢεᵢ (4 candidates, z from rewards [0.1, 0.4, 0.2, 0.9]) has relative L2 error 2.08e-4 and cosine 0.99999998. (ii) rounding of θ': ‖d − ε₁₆‖ / ‖ε₁₆‖ = 0.0054 with d = (θ' − θ)/σ; 0.405% of the elements do not change at all; no changed element changes sign; ‖d‖ / ‖ε‖ = 1.0000.
  - **Limits of that measurement:** one σ, four seeds, unmodified weights, one NumPy version, no reward or learning run; the maximum element-wise relative error of the FP16 cast was 0.747 (its cause was not investigated; inference: very small |ε| values, where FP16 loses relative precision).
  - **Accepted trade-off:** the update moves along ε, not along what the worker actually measured. The rounding error of θ' cannot be removed by any choice of ε. Making it visible (monitoring) is future work, see `TODO.md`, group `monitoring`.
- **[D]** Candidate order is canonical because floating-point addition is not associative: summing in arrival order would make the update depend on network timing.
- **[D — 2026-10-06] Two entry points, one body.** `apply_coefficients_(model, schema, seeds, coefficients, alpha, chunk_elements)` applies GIVEN coefficients (what a worker does when it replays a generation record); `apply_es_update_` is `standardize_rewards` followed by it. The coefficients must be exactly float32 values (a value that would be rounded in silence is refused), finite, a vector as long as the seeds; all zero means no-op. The checks of the other arguments (alpha, chunk size, seeds, model) run before the no-op answer, as before. Test: applying the coefficients of the rewards gives the same bits as applying the rewards (CPU and GPU, several chunk sizes, a large tensor).
- **[D]** Diagnostics: requested update norm, actually applied update (after the FP16 cast), fraction of coordinates that changed, tied-tensor behaviour. **[E]** `milestone2_history.json` reports `update_max_diff = 0.00030517578125` with the worst parameter `model.embed_tokens.weight`.
- Memory note: the largest FP32 `direction` (embedding) is 136,134,656 × 4 B ≈ 545 MB if built for the whole tensor. Every operation is elementwise and the candidate loop is the innermost one, so accumulating one chunk at a time gives the same bits and needs only about one chunk (1 MiB) of FP32 memory.

> **Update 2026-10-06:** `apply_coefficients_` was split out of `apply_es_update_` (the loop over chunks is the same code, line for line); `pytest tests` with the real model gives 992 passed, among them the real-model CPU-equals-GPU check of the update; mutation check of the new function by hand: 10 faults, 8 caught, the 2 others equivalent. Still not run on the 1660S.

> **Implementation status (2026-10-05, evening): implemented, checked on the 5070 Ti only.** `src/heteroes/es/update.py` (`standardize_rewards`, `apply_es_update_`, `UpdateReport`) passes the specification tests (`pytest tests` with the real model: 325 passed; the real-model test compares CPU with GPU bit for bit and keeps the extra GPU memory below 256 MiB). A hand-made mutation check (27 faults) caught everything except two equivalent mutants. Not run on the 1660S. The specification tests exist (`tests/es/test_standardize.py`, `tests/es/test_update.py`; independent NumPy oracle, FP32-versus-FP16 and candidate-order cases chosen so that the data can tell them apart: on 200,000 elements and 8 candidates, FP16 accumulation differed in 111,076 elements and a different candidate order in 41). O4 (canonical epsilon) and the seed checks (integers only, no duplicates, section 3) are decided. Proposed but not approved: the report fields (`noop`, `coefficients`, `requested_l2`, `applied_l2`, `changed`, `numel`).

## 9. Cross-machine same-candidate regression (the gate)

> **Implementation status (2026-10-05, night):** step 6 (one candidate on the 5070 Ti with the code of the package) is done: `scripts/run_one_candidate.py` and the evidence in `artifacts/regression/2026-10-05-one-candidate/`. It covers the checks of the table below on one machine: noise and perturbed-weight hashes (the whole-model hash), restore bit for bit, the 16 predictions (as text) and the reward. **Step 7 (2026-10-06) is also done for one candidate:** the same script at the same commit on the GTX 1660 SUPER, evidence in `artifacts/regression/2026-10-06-cross-machine-one-candidate/`. Identity (hashes of schema, workload, engine, the three weight hashes, seed, sigma, model and tokenizer revision) is equal; the outputs of the 16 questions of the base model, the candidate and the restored model are equal text for text; rewards equal; restore exact on both. The generation config is compared by its SET values (the raw hash differs because transformers 5.17 adds keys with value None and its own version); that rule is pending the owner's approval. Limits: one candidate, one seed, one sigma, 16 prompts, two machines.

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
- **NumPy policy (verified in the NumPy 2.5.3 docstrings):** `PCG64` guarantees that a fixed seed always produces the same integer stream; `Generator` — which provides `standard_normal` — has **no** version-compatibility guarantee ("as better algorithms evolve the bit stream may change"). The NumPy version MUST be recorded (in the environment report of every worker) and the noise behaviour MUST be checked by the self-test of the noise fingerprint (O6, below); the version is not pinned.
- The `ai` environment has NumPy 2.4.5. On 2026-10-02 the five golden vectors of §4.4 were reproduced under it (scratch script). On 2026-10-03 the full-model noise hash (2,105 chunks) was reproduced under 2.4.5 (5070 Ti) and 2.1.3 (Colab, Kaggle) by `scripts/o2_cross_gpu_check.py`, in addition to 2.5.2 and 2.5.3 from the 29/09 probe. **O6 was decided on 2026-10-06: the contract pins the BEHAVIOUR of the noise, not a NumPy version** (see below and section 12).
- **[D — O6 decided 2026-10-06] Pin the behaviour, not the version.** The recipe (section 12) holds a *noise fingerprint*: the hash of the expected digests of five real chunks (`heteroes.noise.selftest`, 13 ms to compute on the 5070 Ti). A worker computes it with its own NumPy before it receives candidates (`noise_selftest()`); a different value means that this NumPy does not generate the canonical bytes and the worker must not be used. The NumPy version is recorded in the environment report of each worker for diagnosis, but it is NOT part of the recipe hash: measured on 2026-10-06, the 5070 Ti (NumPy 2.4.5) and the 1660S (NumPy 2.5.2) generate identical noise, so a version string in the hash would only have split two compatible machines (the two recipe hashes differ if the version is added). Versions that gave identical noise bytes so far: 2.1.3, 2.4.5, 2.5.2, 2.5.3. Limit [inference]: five chunks are a sample; a change of the algorithm of `standard_normal` would almost certainly show in them, and the full-model hash (2,105 chunks) remains the stronger check when the evidence has to be extended.
- Canonical bytes assume little-endian storage (true for both machines).
- Even with identical weights, GPU inference may produce different outputs on different architectures; this is measured separately (§9).

## 11. Decisions needed from the owner

| # | Question | Options | Draft recommendation |
|---|---|---|---|
| O1 | Schema hash for production | (a) include aliases + `schema_version` (hash changes from the probe); (b) keep the probe-compatible hash and validate aliases separately | **DECIDED 2026-10-01: (a)** — MASTER requires aliases in schema identity; portability is re-proven at the gate anyway |
| O2 | Perturbation arithmetic | (a) GPU FP16 `add_`; (b) CPU FP32 then cast; (c) GPU explicit FP32 separate ops then cast | **DECIDED 2026-10-03: (c)**, evidence in §5 (bit-identical on 4 environments incl. the 1660S). (a) kept as a noted alternative (also identical across the 4 environments) |
| O3 | Restore oracle | abs-max diff (current) vs bitwise | **DECIDED 2026-10-01: bitwise** (abs-max only as optional diagnostic) |
| O4 | ε used in the update | canonical FP16 ε upcast to FP32 vs realized difference | **DECIDED 2026-10-05: canonical ε** (option A); measurements and accepted trade-off in §8 |
| O5 | Candidate seed rule | (a) explicit seed list stored in the manifest; (b) derive from (experiment, generation, candidate index) | **DECIDED 2026-10-06:** seeds are explicit in the descriptor (range `0 <= seed < 2^53`); the coordinator chooses them, preferably with `derive_seed`; the frozen regression keeps `[0..3]`. See section 3 |
| O6 | NumPy pin | exact version on both machines (which one?) | **DECIDED 2026-10-06: no version pin; the noise behaviour is pinned** by a fingerprint of five golden chunks checked by a self-test (section 10). The version is only reported |
| O7 | Who computes the update coefficients | (a) every machine recomputes them from the rewards; (b) the coordinator computes them once and they travel | **DECIDED 2026-10-06: (b)**, evidence in section 7 and section 13 |
| O8 | Precision of the forward pass of the evaluation | (a) FP16 (all evidence until G5); (b) FP32 from the FP16 weights (an option of the recipe since G6) | **DECIDED 2026-10-07 (by the owner, implemented the same day): (b) FP32 is the default** of a new recipe, of `build_recipe` and of the scripts (`--eval-dtype float32`), and the default chunk of a worker is the exact size of the precision (FP32: 16, FP16: 1). FP16 stays an option. The cost is 2 GB of GPU memory more per worker and results that are not bit-comparable with the FP16 evidence. Details in section 15 |

## 12. Manifest v1 [D — decided 2026-10-06]

What one logical candidate is, written down so that two machines can check that they run the same one. Two layers.

**Recipe** (`heteroes.manifest.Recipe`; the same for every candidate of an experiment; frozen; its `hash` is what machines compare):

| Part | Fields |
|---|---|
| model | model id, model revision, tokenizer revision, dtype (`torch.float16` only in v1), schema hash |
| noise | engine version (only `numpy_pcg64_normal_f32_to_f16_v1` in v1), `chunk_elements`, noise fingerprint (section 10) |
| perturbation | `sigma` and `sigma_float32` (the exact float32 value, derived from `sigma`, never an independent input) |
| update | the labels of the update numerics of sections 7 and 8 (canonical FP16 epsilon upcast to FP32, FP32 accumulation, population standard deviation computed in float64 with all-zero coefficients below eta, candidates in the listed order) and `reward_eta` |
| workload | workload hash, hash of the SET values of the generation config |

The hash is the SHA-256 of the canonical JSON of that document (`heteroes.canonical`: keys sorted, no spaces, ASCII, no NaN; the same serialization as the schema hash). Not in the recipe on purpose: the NumPy, torch and transformers versions, and `alpha` (a parameter of each generation, not a constant of the numerics; it belongs to the record of a generation), and everything operational.

**Generation config rule [D]:** the manifest hashes the set values of the checkpoint's generation config: the keys whose value is not `None`, without `transformers_version`. Reason [E]: transformers 5.17 (1660S) adds four keys with value `None` and stores its own version, so the raw hash of the dict differs from that of 5.5.0 (5070 Ti) although every set value is equal (evidence of 2026-10-06).

**Candidate descriptor** (`heteroes.manifest.CandidateDescriptor`; small): `recipe_hash`, `parent_weights_sha256` (the whole-model fingerprint of the weights the candidate must be applied to, the model version), `experiment_id` (letters, digits, `_`, `.`, `-`), `generation`, `index` (position in the canonical order of the generation), `seed` (section 3). `candidate_id` is `experiment/g<generation>/c<index>`: the logical job, the same for every attempt and every worker. A field such as worker, attempt, lease, retry, reward or time is refused (`TypeError`): noise must not depend on operational metadata, and those belong to the ledger. Computing `parent_weights_sha256` takes one pass over the whole model (0.6 s on the 5070 Ti, 4.2 s on the 1660S), so it is to be checked once per generation, not per candidate.

**Versioning:** any change of a field, of a label or of the serialization is a new manifest version, not an edit of v1.

**Evidence [E]:** the recipes rebuilt from the records of the 5070 Ti and the 1660S (`artifacts/regression/2026-10-05-one-candidate/`, `artifacts/regression/2026-10-06-cross-machine-one-candidate/`) have the same hash, `1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1` (pinned in `tests/test_manifest.py`; that pinned value was produced by this code, it is a regression guard, not independent evidence). Those records have format 1; `scripts/run_one_candidate.py` now writes format 2, which also holds the recipe, its hash, the descriptor and the result of the noise self-test.

**Not done / open:** the self-test is not yet part of a worker admission (C1); the format-2 script has not been run on the 1660S yet. (The record of a whole generation, listed here before, is done: section 13.)

## 13. Generation record v1 [D — decided 2026-10-06]

What turns the parent weights of a generation into its child weights, as a message: the third layer after the recipe and the candidate descriptor (section 12). `heteroes.generation_record.GenerationRecord`; it does not need the ledger or torch to be read or checked.

| Field | Meaning |
|---|---|
| `experiment_id`, `generation` | which generation (same rules as the descriptor) |
| `recipe_hash` | the numerics (section 12); binds eta, chunk size, engine, schema |
| `parent_weights_sha256` | the weights the update must be applied to (the model version) |
| `seeds` | the seeds in canonical (index) order: integers, `0 <= seed < 2^53`, all different |
| `rewards` | the rewards that were committed, in the same order: finite numbers, stored as floats |
| `coefficients` | the coefficients z of the update, in the same order: **exactly float32 values**, finite |
| `alpha` | the step; finite, fits a float32 (may be zero or negative); `alpha_float32` is derived, never given |

The document also holds `record_version` (1). Its hash is the SHA-256 of the canonical JSON of the document (`heteroes.canonical`). A change of a field, of a label or of the serialization is a new record version. About 744 bytes for 8 candidates, 1,883 for 32, 6,747 for 128 (the FP16 model is 0.99 GB; `artifacts/experiments/2026-10-06-coefficient-residue/`).

**Inputs only [D].** `child_weights_sha256` (the hash of the weights that come out) is NOT in the record: it is an outcome, written apart (`Ledger.mark_applied`); putting it inside would change the hash of the record after the fact.

**The coefficients travel [D — O7].** The coordinator computes them once with `standardize_rewards(rewards, eta)` (`GenerationRecord.from_results` does it); a worker applies them with `apply_coefficients_` and never recomputes them. The rewards stay in the record only so that the coefficients can be audited: `verify_coefficients(eta)` is exact (right for the coordinator that has just made them); `verify_coefficients(eta, atol=...)` is for an audit on another machine, where a coefficient that is `0.0` here may be a residue of 1e-16 there (section 7). All coefficients zero means no signal: the update is a no-op (`record.noop`).

**Write-ahead [D].** The coordinator writes the record into the ledger BEFORE it touches the weights, and marks the outcome after:

```text
generation COMPLETE  ->  record_update(record)        # only if every candidate is committed, and only if the record says exactly
                                                      # what was committed (seeds, rewards, recipe, parent); one per generation
                     ->  apply the update to the weights (apply_coefficients_)
                     ->  mark_applied(record_hash, child_weights_sha256)
```

Recording the same record again is acknowledged; another record for the same generation is a `ConflictingUpdateError` (after a restart the stored one is the one to apply). Marking the same child again is acknowledged; **another child for the same record is an alarm** (the update is deterministic: the same parent and record must give the same child). If the coordinator stops after the weights changed but before `mark_applied`, the record is in the ledger and the update can be redone from the parent checkpoint. The ledger cannot know the alpha and the coefficients are right (they are the coordinator's decision) and trusts the child hash it is given.

**Chain [D — G6].** The `parent_weights_sha256` of generation g+1 is the child of generation g; `Ledger(..., enforce_chain=True)` (the coordinator script turns it on) makes `open_generation` refuse another parent, a generation whose predecessor was not recorded AND marked applied, and a generation without a predecessor (generation 0 may start from any weights). A worker checks its own weights hash against `parent` before it applies a record, and against `child` after.

**Restart [D — G6].** `Coordinator.recover()` finds the place again from the ledger and the published weights: an unfinished generation is resumed from the weights of its parent; a recorded update is applied from the STORED record (never recomputed); an applied one is loaded from its published file, or recomputed from the parent and compared with the child hash that was marked when that file is missing or damaged (a different hash is an error, not a silent choice). The weights of a generation are written and hashed once into a file that is not yet visible, the child is marked in the ledger, and then the file gets its name (`prepare_publication`): a crash at any point leaves a state that `recover()` can finish.

**Not done / not verified [E]:** the restart on two real machines is in the STATUS (failure campaign); two real machines computing the same coefficients (not needed once they travel, and not measured); the effect of a coefficient residue on the real model (only a synthetic NumPy test); applying a record on the 1660S.

## 14. How the noise is executed: threads and pieces [D — decided 2026-10-07, G6]

Generating the noise was 77 percent of a generation (audit of 07/10: 3.7 s per candidate on the 5070 Ti, 9.2 s on the 1660S, and the same again inside the update). Nothing in the contract of sections 4 to 8 is changed by running it in parallel, and this section says why.

- **The identity of a chunk of noise is its address** (section 4.1): schema hash, engine version, candidate seed, parameter index, chunk index, chunk size. Which thread makes it, and when, is not part of it. `noise/parallel.ordered_map` runs the generation of chunks on a thread pool (NumPy's `Generator` releases the GIL while it fills an array), a bounded window ahead of the consumer, and returns the chunks **in the original order**: so every later floating-point operation happens in the same order as with one thread. The number of threads (`HETEROES_NOISE_THREADS`, default `min(16, CPUs)`, 1 = serial) is an execution choice of the machine and is not in the recipe.
- **The arithmetic is elementwise, so the size of the piece it is done on does not change a bit** (the perturbation `fp16(fp32(theta) + fp32(sigma) * fp32(eps))` with its two separate operations, section 5, and the update `acc = acc + eps * z` over the candidates in canonical order, section 8). Consecutive chunks are joined into pieces of about `BATCH_ELEMENTS = 2**22` elements before they go to the device: fewer launches, same bits. The order over the CANDIDATES in the update is still candidate 0 first, element by element. What does change is the order in which the three statistics of the update report (`changed`, `requested_l2`, `applied_l2`) are summed: `requested_l2` and `applied_l2` differ in the last digits from the values of the one-chunk-at-a-time code; the weights do not. The widening of the FP16 noise to FP32 is done on the device (it is exact either way, but doing it on the CPU first cost a single-threaded cast of every element).
- **Evidence [E]** (real model, 5070 Ti, `scripts` of the session; `tests/noise/test_parallel.py`, `tests/es/test_parallel_equivalence.py`): the whole-model hash of the perturbed weights is `8aa3eb9af895cb4a...` (the value of the numerical gate) with 1, 8, 12 and 16 threads and every piece size tested; the weights hash after an 8-candidate update is `41668382d4230d93...` with 1, 8 and 16 threads. Time: perturb 3.69 s -> 0.75 s, update of 8 candidates 44.9 s -> 2.4 s (16 threads). Not measured on a machine with other CPU architecture than the two of the project.
- **Publication [D].** A weights file named `<sha256>.bin` is kept only if its content IS that hash: `Publication.commit()` hashes an existing file of that name and replaces it if it is damaged (a file cut by a crash and still named after the hash would otherwise be served for ever). The file is not fsynced: whoever reads it checks the hash.
- **Taking a downloaded file as the model [D].** A worker hashes the bytes while they arrive (the transfer, not the CPU, is the limit even for a 2012 Xeon: 116 MB/s against 275 MB/s of SHA-256); after the copy to the GPU it COMPARES the model's snapshot with the file instead of hashing the model again (`CandidateExecutor.reset_parent(sha, verified_file=path)`): the same guarantee (the model is those bytes, so it has that hash) at the speed of memory. A SHA-256 of the whole weights costs 3.6 s on the 1660S's CPU, and the old synchronization did it four times.

## 15. Precision of the forward pass of the evaluation [D: FP32 is the default since 2026-10-07 (O8), FP16 an option]

**What was found [E].** The greedy answer to a prompt is an argmax over scores computed in FP16, so it flips whenever the two best scores are closer than the rounding noise of the computation. Two things change that noise without changing the model: a prompt in a batch with others (left padding changes the shapes and the order of the sums), and another GPU (another kernel). On the 5070 Ti, with the stack of the 1660S (torch 2.13+cu132, transformers 5.17; the same counts were obtained with torch 2.10 and transformers 5.5, so it is not the software stack):

| 33 states (the parent and 32 candidates) x 16 prompts | prompts whose answer differs from "one prompt per call" |
|---|---|
| FP16, a batch of 16 prompts | 16 of 528 |
| FP16, batches of 2 | 9 of 528 |
| FP16, scores of the output projection in FP32 only | 17 of 528 and 8 of 528: the noise is in the layers, not in the last matrix |
| **FP32 forward pass from the same FP16 weights**, a batch of 16 | **0 of 528** |
| FP32, batches of 2 | 0 of 528 |
| FP16 or FP32, a batch of one with padding enabled (no padding actually added) | 0 |

The margin between the two best scores at the flip is 0 to 0.09 on scores of magnitude 16 to 32 (the spacing of FP16 there is 0.0156 and 0.0312): exact ties and one-unit differences, as expected from numerical noise, never a large margin (`scripts/cross_gpu_sweep.py ladder`, `src/heteroes/eval/diagnostics.py`, `artifacts/experiments/2026-10-07-g6-cross-gpu/`). In G4 the same effect made "every chunk above 1 inexact".

**The option and the default [D].** `Recipe.eval_dtype` (`"float32"`, the default of a new recipe since O8, or `"float16"`). The DOCUMENT is unchanged by the change of default: an FP16 recipe leaves the key out (a document without the key means FP16, `LEGACY_EVAL_DTYPE`) and has exactly the document and the hash of manifest v1 (`1604737e...`); an FP32 recipe has an `eval_dtype` key in `workload` and the hash `efc1ff67...` that the FP32 runs of G6 recorded, so no recorded hash changed and a worker with the other precision is refused at admission like any other difference. What changed is only what a recipe built WITHOUT saying the precision is: FP32 (code that wants the FP16 evaluation of the earlier evidence must say `eval_dtype="float16"`, as `run_one_candidate.py` and the reading of the format-1 records do). The default chunk of a worker is `eval.precision.default_chunk`: 16 for FP32 and 1 for FP16 (an explicit `--chunk` still wins). Only the FORWARD PASS of the evaluation changes: the weights, the noise, the perturbation, the restore, the update, the hashes and the synchronization stay FP16 / FP32 as in sections 4 to 8. `heteroes.eval.precision.EvalModel("float32")` keeps a float32 copy of the model (about 2 GB more on the GPU) and refreshes it from the live FP16 weights before each evaluation (FP16 to FP32 is exact, so nothing is lost; the tie between the embedding and the output projection is kept).

**Cost [E, 5070 Ti, the 16 prompts of the workload, one evaluation]:** FP16 one prompt per call 0.79 s (the reference path of G3 to G5); FP16 in one batch 0.13 s but not exact; FP32 one prompt per call 0.99 s; **FP32 in one batch of 16 0.16 s**. A candidate (perturbation, evaluation, restore) takes 1.02 s in FP32 with chunk 16 against 1.61 s in FP16 with chunk 1. The probe of `profile_worker.py` with `--eval-dtype float32` found chunks 1, 2, 4, 8 and 16 identical to chunk 1 on the parent and on 32 perturbed candidates: the safe chunk is 16.

**What it does to the rewards [E]:** on the same GPU, the FP32 evaluation changed the answer text of 37 of 1,920 prompts (1.9 percent) over 120 candidates and the reward of 1 of the 120 candidates (`compare-5070ti-fp16-vs-fp32.json`). It is a new recipe, not a refinement: results of FP16 and FP32 runs are not comparable bit for bit.

**Between two GPUs [E]:** the same 120 candidates (seeds 0 to 119, sigma 1e-3, 16 prompts each, one prompt per call) on the 5070 Ti and on the 1660S, both on torch 2.13.0+cu132 and transformers 5.17.0 (`artifacts/experiments/2026-10-07-g6-cross-gpu/`). **FP16: 33 candidates have a different answer text on the other GPU (36 of 1,920 prompts, margins at the flip 0 to 0.043), 1 candidate a different reward** (seed 43: 0.25 against 0.1875). **FP32: 0 of 1,920 prompts differ, 0 rewards.** At run level (`../2026-10-07-g6-benchmark-*`): all 20 FP32 runs of the benchmark (one or two GPUs, any assignment of the candidates) ended with identical rewards and weights hashes; of the 6 FP16 runs that used the 1660S, 2 ended with other weights (candidate 13 of generation 2 scored 0.3125 on the 1660S and 0.25 on the 5070 Ti). With no difference in 1,920 prompts the 95 percent upper bound of the per-prompt rate is about 0.16 percent (rule of three): a checked level on this software and these two GPUs, not a guarantee.

**Decided 2026-10-07 (O8): FP32 is the default of the experiments.** For: exact batching (a 5 times faster evaluation) and the same answers on both GPUs (0 of 1,920). Against, and accepted: 2 GB of GPU memory more per worker (the 1660S has 6 GB; the FP32 benchmark ran on it), a recipe change that makes the earlier evidence (all FP16) not directly comparable, and the claim is a checked level (1584 padded-batch comparisons without a difference), not a guarantee. The FP16 option stays for comparison with that evidence.

## 16. The CUDA noise engine [E for two GPUs (07/10/2026, G7); an option of the recipe since the same day, the CPU engine stays the default]

**The problem it answers.** The canonical engine (sections 3 and 4) makes the noise on the CPU: 0.7 s per candidate on the 5070 Ti, 3.7 s on the 1660S and 0.3 s per candidate again in the
coordinator's update. The native GPU noise (`torch.Generator` on a CUDA device) is fast but depends on the GPU for a big tensor (below).

**What was found [E]** (`artifacts/experiments/2026-10-07-g7-restore-tradeoff/`, README sections 3 and 4). The random kernel of PyTorch runs `min(ceil(numel / 256), SMs x (max threads per SM / 256))`
blocks of 256 threads; thread t writes the elements t, t + T, t + 2T, t + 3T with T = blocks x 256. While a call makes at most T elements the number each element gets does not depend on the
GPU. `torch.randn` with the same seed gave the same bytes on the RTX 5070 Ti and the GTX 1660 SUPER for every size up to 22,528 elements (88 blocks, the 1660S) and different bytes from 22,529
(and for a sequence of calls of 32,768 or 65,536; calls of 8,192, 16,384 and 22,528 agree). The maths of the generator (log, sin, cos) gave the same bits on sm_75 and sm_120.

**The engine [D as a candidate, not yet decided for use]** (`heteroes/noise/cuda_engine.py`, `heteroes/es/cuda_ops.py`). Version `torch_cuda_philox_chunked_f32_to_f16_v1`:
- the noise of one tensor is a SEQUENCE of calls of `CUDA_CALL_ELEMENTS` = 22,528 elements (the last shorter) on one `torch.Generator` seeded with the first 63 bits of the SHA-256 of
  `engine version | candidate seed | schema hash | parameter index | call size` (like the address of a chunk in section 4, without the chunk index);
- float32 normal cast to float16 (round to nearest even), then exactly the arithmetic of sections 5 (O2 = c) and 7 to 8 (FP32 accumulation in candidate order); only the source of eps changes;
- the pieces in which the noise is applied to the weights are any multiple of the call size and do not change the bits; the restore stays the snapshot restore (section 6);
- it needs a CUDA device even to reconstruct noise (the coordinator too), `check_device` refuses a GPU with fewer than `CUDA_CALL_ELEMENTS / 256` blocks of the kernel, and
  `check_cuda_noise_selftest` compares a fingerprint of five golden tensors (`EXPECTED_CUDA_NOISE_FINGERPRINT`, equal on both GPUs).

**Evidence [E].** On the real model, on both machines, equal hashes of all the weights after a perturbation (seeds 0, 1, 2), after the restore, and after an update of 8 candidates, and an equal
fingerprint (`cudaengine-5070ti.json`, `cudaengine-1660s.json`: 8 of 8 hashes). Times, whole model: perturbation 0.08 s (5070 Ti) and 0.58 s (1660S) against 0.73 s and 3.67 s with the CPU engine;
update of 8 candidates 0.64 s against 2.4 s. 72 tests pass on the 5070 Ti and 49 (the engine's) on the 1660S; mutation check on a scratch copy: 18 of 22 and 10 of 11 faults caught, the others equivalent
or invisible (one writes past a buffer with the right values).

**What it relies on [OPEN risks].** That curand keeps giving the same bits on these two architectures (nobody guarantees it) and that PyTorch keeps its thread mapping: both change with the torch or
CUDA version, so the fingerprint must be checked at admission and the torch version recorded; a GPU with fewer than 88 blocks (for example a GTX 1650, 56) is refused at the call size of 22,528;
only two GPUs and one software stack were compared. The native noise of the machines is NOT portable beyond the call size (arms C of the experiment give different drift on the two GPUs).
It is a different noise from engine v1: results are not comparable bit for bit. **It is an option of the recipe** (`noise.engine_version` = `torch_cuda_philox_chunked_f32_to_f16_v1`, `noise.chunk_elements` = 22,528 and `noise.fingerprint` = the engine's, all three checked by `Recipe`; the document of a CPU recipe and its hash are unchanged, so manifest v1 is extended, not changed). The executor perturbs with it, the coordinator applies the update with it, every worker and the coordinator run `check_cuda_noise_selftest` before taking part, and a recipe may also name a workload (`workload.name`, see below).

**In a real distributed run [E]** (`artifacts/experiments/2026-10-07-g7-cluster-benchmark/`): coordinator, 2 workers on the 5070 Ti and one on the 1660S, 24 candidates, 4 generations, 3 runs per cell: all 9 runs with the CUDA engine ended with the same rewards and the same weights hash although the 1660S evaluated 9 to 13 candidates of each run; against the single-process reference the end-to-end test is bit-equal (`tests/test_e2e_local.py`). A generation is 7.4 to 10.2 percent shorter than with the CPU engine in the same condition.

**A named workload [D].** `Recipe.workload_name` is `arith16` (the 16 prompts of the contract, left out of the document, hash unchanged) or `cot_l3_q32` (`heteroes/eval/cot_workload.py`: generated word problems, 32 questions, step-by-step reasoning, up to 256 new tokens, reward = exact integer after the last `Answer:` line, else the last integer; its own `workload_hash` over the system prompt, the budget, the sampling flag, the reward type and every question with its answer). It is a different recipe.

**The chunk of the prompts is an execution choice [E for the long workload, 07/10/2026].** The number of prompts per `generate()` call is not in the recipe. With the FP32 forward pass, chunks 16, 32 and 64 gave the same answers for the long workload (64 questions) on the parent and on 24 perturbed candidates of the CUDA engine, on both GPUs and between them (0 of 1,600 answers differ in each comparison, `artifacts/experiments/2026-10-07-g7-restore-tradeoff/chunkprobe-*.json`); a bigger chunk makes a candidate 1.6 to 3.3 times faster (`rollout-scaling-*.json`). It is a checked level, not a guarantee (about 0.2 percent per answer at 95 percent confidence): repeat the probe for another model, workload or software version.

**Restore by arithmetic is not used.** Coming back by `-sigma` is not exact: after 24 candidates 25 percent of the FP16 elements differ from the original (relative L2 1.4e-4, growing like the square root of
the number of candidates); the snapshot restore costs 0.14 s on the 5070 Ti, which is 3 percent of a candidate of the long workload.

## 17. How the answers are generated: the decode engine, and what equal texts are worth [E for FP32 on three GPUs; an option of the recipe since 09/10/2026, `hf_generate` stays the default]

**The choice.** `Recipe.decode_engine` is `hf_generate` (the library's `generate()`, the default, left out of the recipe document so that no earlier hash changes) or `hf_compact` (`heteroes/eval/compact_decode.py`:
a greedy decoding loop that removes the answers that have ended from the batch). It is for the long workloads only (`arith16` has its own code and refuses it). It is in the recipe because the two
can give different texts in a rare tie (below), so every worker of an experiment must use the same one. The constants of `hf_compact` (the fraction of ended rows that triggers a removal, 0.1) are part of the engine: a change of
one is a new engine name.

**What `hf_compact` reproduces and what it refuses.** Left-padded prompts, the position ids from the attention mask, the logits processors of the model's generation config in greedy mode (only the repetition
penalty is supported: any other raises `UnsupportedDecode` before anything is decoded), all the end tokens, padding after the end of an answer, the same width of output as `generate()`. A key/value cache that cannot select rows makes it
go on without removing any (correct, not faster; `stats["compaction_supported"]`).

**Evidence** (`artifacts/experiments/2026-10-09-compact-decode/`, `-rollout-waste/`, `-decode-profile/`; all FP32, greedy, 128 questions, parent and noisy candidates; the AI's own scripts, not reviewed by the owner):
* On the project's workload (Qwen2.5-0.5B, `cot_l1_q128`) the 5070 Ti, the first 3060 and a second 3060 in another city gave the SAME texts as `generate()` in all 18 comparisons each (parent and 8 candidates, chunks 64 and 128), and the three machines gave the same texts as each other.
* Other models and tasks (SmolLM2-360M, Qwen2.5-0.5B, Qwen3-0.6B; GSM8K, countdown, 4x4 sudoku; 9 pairs of 768 comparisons each): 0 differing texts in 8 pairs; one pair (Qwen2.5-0.5B on GSM8K) had 1 differing text of 768 (below). Qwen3-0.6B was run at chunks 16 and 32 on GSM8K and countdown because its key/value cache is 9 times bigger and 64 and 128 ran out of memory.
* Speed: 1.1 to 2.4 times faster than `generate()`, more when the answers are shorter than the limit and unequal in length; the saving is the wasted token slots (at chunk 64, 56 percent of the slots held an answer that had ended). Reading the "ended" flags back to the host less often changed nothing.
* Half precision: FP16 gave 28 differing texts of 768 and BF16 39 of 384 (Qwen2.5 and Qwen3 on GSM8K): the contract's choice of FP32 (section 15) is kept; `hf_compact` is meant for FP32.

**What equal texts are worth: NOT a guarantee.** Greedy decoding is bit-stable only up to the rounding noise of the arithmetic. On Qwen2.5-0.5B, GSM8K, candidate 7002, question 15, `generate()` itself gives two different texts at chunk 128 and at chunk 64 (and `hf_compact`
agrees with chunk 64): at generated token 165 the two best tokens ` do` and ` perform` have scores 23.851572 and 23.851578, 5.7e-6 apart (`general/diagnose_flip2.out`). Such a tie is broken differently by any
change of the batch shape or of the GPU. Measured rate: 1 text in 768 on GSM8K (about 290 tokens per answer), none on the project's short workload and on the other tasks. A flipped token changes everything after it, so the effect on a REWARD depends on the task and
cannot be inferred from the text; it has to be measured per task. Consequence: with long answers "the same candidate gives the same reward on every worker" is probable, not certain, and two runs of one experiment can end with different weight hashes (replay is not
affected: it uses the recorded rewards). Ideas, not tried and left to the owner (`TODO.md`, `near-ties`): a margin guard in the decoding loop, a reward-level tolerance per task.

**Open:** not run on the GTX 1660 SUPER (it was down), nor on other architectures (Ada, Blackwell other than the 5070 Ti); vLLM would remove the same waste but its equality of texts across GPUs, the in-place perturbation of the weights and the installation on WSL2/Turing/Blackwell are unchecked.

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
