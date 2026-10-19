# ADR-008 — Recipe v3: one format, coordinator scoring and extensible experiments

Status: **DRAFT** (2026-10-19). The eight owner decisions it implements are DECIDED; the concrete rules below are PROPOSED
until the owner accepts this ADR. Related: ADR-001, ADR-002, ADR-007 (its "Recipe, noise, update, replay formats" row is
superseded by section 9 once this ADR is accepted).

Labels: **[CODE]** exists in the tree · **[DECIDED]** owner decision of 2026-10-19 · **[PROPOSED]** this draft ·
**[OPEN]** needs an owner answer.

## Context

Today an experiment is either a Recipe v1 (`manifest.py`: four built-in workloads, pinned Qwen) or a Recipe v2
(`study/recipe.py`: imported numeric-answer datasets, three models), and v2 wraps v1 through `__getattr__`. Reward is
computed on the worker and is always exact-number accuracy (`executor.evaluate_task`). Nobody can bring their own reward,
answer format, weight space or ES coefficient rule without editing the runtime and shipping a new desktop release.

The owner decided (2026-10-19 audit, Q1–Q8):

1. Reward is computed **on the coordinator** from texts the worker submits. [DECIDED]
2. Texts are **ledger data**: the first committed attempt wins; replay re-scores stored texts; drift is caught by sampled
   re-execution on another machine. [DECIDED]
3. The scorer's identity (name@version + code hash) is **outside the recipe**, frozen per generation. [DECIDED]
4. The shared lab accepts only **declarative** scorers; Python scorers run only on a coordinator the researcher hosts. [DECIDED]
5. Weight spaces **full, subset and LoRA**; LoRA results are never mixed with full-parameter results. [DECIDED]
6. v1 and v2 **merge into one format**, numerics unchanged, old runs must replay to their recorded hashes. [DECIDED]
7. **One** identity break (v3, desktop r11) that also makes room for antithetic sampling and coefficient rules. [DECIDED]
8. SDK/CLI and web are built in parallel on one spec and one runner, after the shared core. [DECIDED]

## Decision

### 1. Three documents, three hashes [PROPOSED]

| Document | Who must agree on it | Hash used for |
|---|---|---|
| **Recipe v3** | every worker and the coordinator | `recipe_hash` in descriptors, ledger, records (as today) |
| **Plan** | the coordinator only | experiment identity; population, generations, α, coefficient rule |
| **Generation context** | frozen in the ledger before a generation opens | sigma, batch, scorer of that generation |

A worker never needs the plan or the scorer: changing the scorer or α does not change what a worker computes, so it must
not change `recipe_hash` (decision 3). Every field is written explicitly: no "default left out of the document" rule, which
v1 needed four times (`manifest.py:187-189`) and which makes each new option a special case.

### 2. Recipe v3 document [PROPOSED]

```
{"formatVersion": 3,
 "model":       {"id", "revision", "tokenizerRevision", "dtype": "torch.float16", "files": {name: sha256} | null},
 "weightSpace": {"kind": "full"} | {"kind": "subset", "include": [regex, ...]}
              | {"kind": "lora", "rank", "alpha", "targetModules": [...], "initialAdapterSha256"},
 "schemaHash":  hash of the TRAINABLE schema T (section 4),
 "noise":       {"engine", "chunkElements", "fingerprint"},
 "perturbation":{"sigma": {"kind": "constant"|"cosine", "initial", "minimum", "generations" | null}, "antithetic": bool},
 "evaluation":  {"evalDtype", "decoder", "generationConfigSha256", "maxNewTokens", "systemPrompt" | null},
 "data":        {"kind": "builtin", "name", "hash"}
              | {"kind": "dataset", "contentHash", "splitHashes", "batch": {"size", "seed", "sampler"}}}
```

Serialization: the one canonical JSON of `heteroes.canonical` [CODE]. Unknown keys or versions are refused. `files` may be
`null` only in a document translated from v1 (whose files were pinned by revision only). The scorer, rewards, α, η and the
coefficient rule are deliberately absent.

### 3. Plan and generation context [PROPOSED]

Plan: `{"formatVersion": 1, "recipeHash", "population", "generations", "alpha", "coefficientRule": {"name", "version",
"eta"}, "scorer": {"kind": "declarative"|"python", "name", "version", "codeSha256" | null, "config"}}`.

Generation context (the existing `generation_context` table, `ledger.py:452` [CODE]) gains `scorer` and `coefficientRule`
next to `sigmaFloat32`, `batchHash` and `batchIndices`. A Python scorer whose code hash differs from the frozen one is
refused before scoring (decision 3); a scorer change starts at a generation boundary and is visible in the ledger.

### 4. Weight spaces as a trainable schema T — no change to noise or ES code [PROPOSED]

Perturbation, restore, update and the noise address all iterate over the schema they are given and address noise by
`(seed, schema_hash, parameter_index, chunk)` (`noise/contracts.py:17-58`, `es/update.py:115-176`) [CODE]. A weight space is
therefore only a rule that builds **T**:

- **full**: T = every floating parameter, exactly today's `build_parameter_schema` (same hash: full-parameter v3 noise is
  bit-identical to v1/v2 noise).
- **subset**: T = the parameters whose canonical name or alias matches an `include` regex, in model order; a tied tensor is
  in T if any of its names matches. T has its own hash, hence its own noise.
- **lora**: the base model is frozen and pinned by `model.files`; T = the adapter parameters (FP16) created by the pinned
  configuration; the initial adapter is a published file named by `initialAdapterSha256` (no random initialization on
  workers). With PEFT's B = 0 initialization the first-order effect of a perturbation is σ·ε_B·A ≠ 0, so learning starts.
  [CODE since 2026-10-19: `model/lora.py`, PEFT 0.21.2 pinned as the runtime's `lora` extra; not yet in the desktop
  worker profile, which is r11 work.]

`parent_weights_sha256` becomes the hash of T's tensors (today T = all, so nothing changes for full). Publication and
synchronization move only T: a LoRA or subset update ships megabytes, not 1 GB. LoRA runs are a different search
distribution: the web and the SDK label them and never put them on one chart with full-parameter runs (decision 5).
What changes is `model/schema.py` and loading — neither is frozen. A subset schema has its own version
(`heteroes.parameter_schema.v1.subset`, [CODE] since step 1) and keeps the full schema's entries unchanged, original
index included; `resolve_tensors` accepts it only as an ordered selection of the model's entries, while a full schema
must still match the model exactly (a model with an extra parameter is refused). A subset does not pin the parameters
it leaves out: `model.files` does.

### 5. Antithetic sampling without touching frozen code [PROPOSED]

- Descriptor gains `sign` ∈ {+1, −1}. With `antithetic: true`, candidates 2k and 2k+1 share seed
  `derive_seed(experiment, generation, k)` [CODE `manifest.py:284`] with signs +1, −1; `population` must be even.
- Perturbation uses scale `sign·σ_f32`: `perturb` only requires a finite sigma (`es/checks.py:15-17`) [CODE], and IEEE
  multiplication is sign-symmetric, so `fp32(−σ)·fp32(ε) = −(fp32(σ)·fp32(ε))` bit for bit.
- Coefficients are computed per candidate (rule of the plan, in canonical candidate order). For the update, each pair is
  merged into ONE coefficient for its seed: `c_k = float32((float64(c⁺) − float64(c⁻)) / 2)` — the difference and the
  halving are exact in float64, so this rounds once. `apply_coefficients_` then receives unique seeds (its duplicate check,
  `es/update.py:138-140`, stays) and divides by the number of seeds, N/2, so the step equals Σᵢ sᵢcᵢεᵢ / N.
- Without `antithetic`, the coefficients go to `apply_coefficients_` unchanged: today's update, bit for bit.
- Ledger: `UNIQUE (experiment_id, generation, seed)` becomes `UNIQUE (experiment_id, generation, seed, sign)`.

### 6. Coefficient rules [PROPOSED]

A rule is a pure function `rewards (float64, canonical order) → coefficients (float32)`, named and versioned, recorded in
the plan, the context and the generation record. `zscore@1` is today's `standardize_rewards` (`es/update.py:29-52`)
[CODE] and stays the default; `centered-rank@1` is the next one. Rules with state (momentum, Adam) are rejected: the record
would no longer be "seeds + coefficients + α" and replay would need optimizer state.

### 7. Scoring on the coordinator [PROPOSED]

- Worker protocol v3: `submit_result {"descriptor", "attempt_number", "token", "completions", "completionsSha256"}`
  instead of `"reward"` (`worker_api.py:9` [CODE]). `completionsSha256` = SHA-256 of the canonical JSON list of texts.
- The coordinator checks the hash, stores the texts, runs the frozen scorer and commits the reward in the same
  transaction. Per-row scores must be finite; the reward is their mean (`mean@1`).
- **A scorer failure is never a reward of 0 and never the worker's fault**: the generation pauses with the error. An
  infrastructure failure on a worker stays a typed failure (ADR-002).
- Declarative scorers v1 reuse today's rules exactly: `answer-line-last-number@1` (v2, `study/evaluation.py:9-18`),
  `last-integer@1` (arith16, `eval/workload.py:74-85`), `answer-line-integer@1` (cot workloads,
  `eval/cot_workload.py:71-79`); new ones: `regex@1`, `exact-string@1`, `choice-letter@1` (A–D).
- Python scorers (self-hosted coordinator only): `f(completions, rows) -> list[float]`, identified by name@version and the
  SHA-256 of their source files; a lab built for others refuses them (decision 4).
- Built-in workloads keep their numbers: their scorer on the stored texts gives the same rewards as today's workers.

### 8. Storage, replay and audit [PROPOSED]

- Ledger schema 6: `candidate.sign`, a `completion(candidate_id, attempt_number, sha256, body)` table (zlib-compressed
  canonical JSON; about 15 KB per candidate at 32 rows × 512 tokens), the scorer and rule in the context. [OPEN Q-A]
- Replay of a v3 run: apply records (seeds, signs, coefficients, α) → child hashes; **re-scoring** stored texts must give
  the recorded rewards and coefficients exactly.
- Sampled audit: a deterministic ~5 % of committed candidates (by hash of candidate id) is re-executed as an audit attempt
  on another worker; equal `completionsSha256` is a pass. A mismatch never changes the committed reward. [OPEN Q-B]

### 9. One format break, and the old formats [PROPOSED]

- After the switch the coordinator creates and runs **only v3**. v1/v2 documents become read-only inputs: a translator
  turns each into a v3 document and plan, and a mapping table `old recipe hash → v3 recipe hash` is written into a NEW
  evidence folder; `runtime/artifacts/` and old evidence are never rewritten (AGENTS.md).
- Old runs are replayed, never continued: an unfinished v1/v2 experiment must end before the switch.
- **Numerics are unchanged.** Acceptance: every recorded identity in `tests/test_golden_identities.py` still holds; for
  every recorded CPU-engine run whose initial weights are available, replay from the translated documents reproduces the
  recorded child hashes; CUDA-engine runs need the owner's GPU authorization.
- Rollout: r11 desktop workers speak v3; the server assigns v3 work only to devices that advertise `recipeVersions` with
  3 (`device_models.py:46` [CODE] today allows [1, 2]); r10 devices receive a clear "update to r11" state instead of work.
  Windows has never been qualified for v2 (`policies.py:53` [CODE]); r11 needs a real Windows v3 acceptance. [OPEN Q-C]

### 10. Where code may change

| Area | Change | Frozen? |
|---|---|---|
| `noise/`, `es/` | none (sections 4–6 reuse them as they are) | frozen — untouched |
| `generation_record.py` | record v2: signs, rule, scorer identity | frozen — needs this ADR accepted |
| `ledger/` | schema 6 (section 8) | frozen — needs this ADR accepted |
| `worker_api.py`, `worker*.py`, executor | protocol v3, texts instead of reward | needs this ADR accepted |
| `model/schema.py`, `model/loading.py` | trainable schema T, LoRA loading | not frozen |
| new `heteroes/v3/` | documents, translator, scorers, antithetic merge | new, pure functions |

## Open questions for the owner

- **Q-A** Texts in the ledger (compressed, atomic with the reward) or in content-addressed files next to it? Proposed: in
  the ledger.
- **Q-B** On an audit mismatch: notify only, or quarantine after N mismatches? Proposed: notify, quarantine after 3.
- **Q-C** Does r11 keep a v1 worker for a transition period, or is the switch a flag day? Proposed: r11 speaks v1 and v3,
  r12 drops v1.
- **Q-D** Antithetic on by default for new experiments? Proposed: off by default in v3.0, chosen per experiment.

## Consequences

Researchers change reward, answer format, data, weight space and coefficient rule without touching the runtime; workers
need an update only when the worker contract (recipe v3) changes. Costs: a ledger and protocol migration, an r11 release
with Windows acceptance, larger ledgers (texts), and a translator that must be kept for as long as old runs are replayed.

## Not decided here

The Python SDK surface (`ESTrainer`), the web forms, async generations, decoders other than HF (vLLM), and BF16 or
quantized bases for models above 1B.
