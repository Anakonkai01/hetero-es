# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

HeteroES-LLM: a synchronous Evolution Strategies (ES) post-training runtime for small heterogeneous consumer-GPU clusters (currently RTX 5070 Ti 16 GB + GTX 1660 Super 6 GB, connected over LAN/Tailscale). It is a **software/distributed-systems project with a numerical core**, not a new ES algorithm or scheduler. Two-person capstone; this repo is the Systems/Core track (owner "A").

Contributions are organized as C1 (admission: who may/should work), C2 (execution policy: who gets which work), C3 (candidate/attempt/lease correctness under failure), C4 (canonical model state: sync/replay consistency). "C4" here is **not** the C4 architecture model.

## Context documents — read before architecture-level changes

- `HETEROES_LLM_MASTER.md` — what the system *should be*: scope, architecture, numerical contract, C1–C4, roadmap, claim boundaries (mostly Vietnamese). Never put transient status here.
- `HETEROES_LLM_STATUS.md` — what is *actually true now*: verified evidence, failures, blockers, artifacts, exact next action. Roadmap dates in MASTER are targets, not evidence.
- `TODO.md` — short list of code-level clean-up items (not status, not roadmap). Delete an item when it is done; code-level `TODO(...)` comments in `src/` are listed there by group.
- `HANDOFF.md` — working-style rules and the engineering sequence (bootstrap-era document; its "current state" sections are outdated, see its header note).
- `notebooks/ES_Milestone1_2_modified.ipynb` — historical numerical prototype (functions like `build_parameter_schema`, `find_parameter_aliases`, `apply_perturbation`, `es_update_direction`, `restore_canonical_parameters`, `run_es_generation`). Its saved outputs are mixed/stale; it is **not** a clean Run-All artifact. Do not grow it into the framework; port logic into `src/heteroes/` with tests.
- `docs/architecture.md` — big picture: one ES generation end to end, components, identity layers, state ownership, alternatives.
- `docs/numerical-contract.md` — exact numerical rules (schema, NoiseEngine v1 byte recipe, golden vectors, perturb/restore/update, the cross-machine gate) and open decisions O1–O6. Rules are tagged [E]vidence / [D]ecided / [P]roposed / [OPEN].
- `docs/adr/` — architecture decision records (ADR-001: CPU PCG64 noise engine).
- `artifacts/probes/2026-09-29/` — raw probe scripts + JSON evidence (byte-identical copies, checksums in its README). Never edit; add new evidence in a new dated folder.

## Working style (from the handoff — important)

**This is not a vibe-coding project. Every file creation/edit/deletion, state-changing command, commit, and design decision must be proposed and explicitly approved by the user first.** Reading and analysis are fine without asking.

The user is an experienced software engineer new to ES, numerical reproducibility, and distributed correctness. Act as senior engineer + tutor:

- Before a non-trivial module: explain where it sits, the problem, inputs/outputs, invariants, design choices; then implement a small piece, test it, explain the result. Commit only after the step is understood and passes.
- Frame each step as Objective / Why / Inputs / Outputs / Invariants / Verification / PASS–FAIL.
- Don't dump large code blocks to paste blindly. Map concepts to familiar SE ideas (schema ≈ contract, CandidateDescriptor ≈ immutable job DTO, lease ≈ temporary job ownership, NoiseEngine ≈ pure deterministic function, cross-machine regression ≈ contract test across implementations).
- Don't invent ES behavior, prior-art behavior, or numerical guarantees; check source or label as inference.

## Implementation order — do not reorder casually

1. ParameterSchema / numerical contract → 2. production CanonicalNoiseEngine → 3. unit/contract tests → 4. route all perturb/reconstruct/update paths through the one engine → 5. FP32 update accumulation + notebook numerical debt → 6. local regression → 7. cross-machine same-candidate regression (5070 Ti vs 1660S) → 8. freeze candidate/noise manifest v1 → 9. commit + evidence + STATUS update.

Only after that gate: minimal worker/coordinator HTTP, one remote candidate, frozen two-node generation, SQLite ledger, fake-worker fault tests, C1/C2, sync experiments. **No FastAPI/scheduling/DB/Docker work before the cross-machine same-candidate regression passes.** Docs planned for this phase: `docs/architecture.md`, `docs/numerical-contract.md`, `docs/adr/ADR-001-canonical-noise-engine.md` — only these, not the full docs tree.

Modules (implemented): `src/heteroes/model/schema.py` (ParameterSchema, see `docs/numerical-contract.md` §2 status note), `src/heteroes/noise/contracts.py` (`ChunkNoiseAddress`, `ParameterNoiseAddress`) and `src/heteroes/noise/engine.py` (CanonicalNoiseEngine v1). Not yet written: perturb, restore, ES update (`src/heteroes/es/` is empty). Tests mirror packages under `tests/{es,model,noise}/`. `scripts/o2_cross_gpu_check.py` is a self-contained cross-GPU check (it contains a *copy* of the engine so it can run on Colab/Kaggle; the package engine is the only production implementation).

Decided so far: O1 (2026-10-01) — production schema hash includes aliases and `schema_version`; O3 (2026-10-01) — restore oracle is bitwise; O2 (2026-10-03) — perturbation arithmetic is option (c), see below. Still open: O4, O5, O6 (see contract §11). Code-level TODOs live in `src/` (`grep -rn TODO src/`).

## Numerical contract (non-negotiable invariants)

- **Native CUDA RNG is not canonical.** `torch.randn_like(..., device="cuda")` with the same seed produced different noise on the two GPUs even with matched torch/CUDA/transformers. Never use it for cross-worker candidate identity.
- **CanonicalNoiseEngine v1** (`numpy_pcg64_normal_f32_to_f16_v1`): logical chunk identity (schema hash, engine version, candidate seed, parameter index, chunk index, fixed `chunk_elements`) → SHA-256 → first 128 bits little-endian → NumPy `PCG64` → standard normal in FP32 → cast/apply as FP16. `chunk_elements = 262144`. Verified byte-identical over the full model (2,105 chunks) in four environments — RTX 5070 Ti, GTX 1660 SUPER, Colab T4, Kaggle T4 — with NumPy 2.1.3, 2.4.5, 2.5.2, 2.5.3 (`artifacts/regression/2026-10-03-o2-perturbation/`); still pin and record the exact NumPy version — NumPy's `Generator` (which provides `standard_normal`) explicitly has no cross-version stream guarantee. Golden chunk hashes (probe schema hash and production schema hash) are in `tests/noise/test_engine.py` and `docs/numerical-contract.md` §4.4.
- **Perturbation arithmetic (O2 = c):** `fp16( fp32(θ) + fp32(σ)·fp32(ε) )`, with the multiply and the add as **separate** eager PyTorch operations (`t = ε.float() * σ`, then `(θ.float() + t).half()`). Do not use `add_(eps, alpha=sigma)`, all-FP16 arithmetic, a fused kernel or `torch.compile` for canonical perturbation — those either were measured non-portable or would need re-verification with `scripts/o2_cross_gpu_check.py`. σ is recorded as its exact float32 value.
- **One implementation only**: worker perturbation, coordinator reconstruction, ES update, replay/debug, and regression all call the same engine.
- Noise identity must NOT depend on operational metadata (worker_id, attempt_id, lease, retry number, reward, workload, arrival time). A retry on another worker reconstructs the same noise. Chunk identity is independent of execution order.
- **ParameterSchema** defines canonical order/name/shape/dtype/numel and alias (tied-weight) mapping; the alias map is part of the schema hash. Discover aliases with `named_parameters(remove_duplicate=False)`; a group has aliases when `len(names) > 1` (the notebook's `> 2` was a bug; Qwen has exactly 1 tied group: `model.embed_tokens.weight` + `lm_head.weight`). Tied params get one perturbation entry. `id(param)`/`data_ptr()` may be used only as in-process keys — never serialized or hashed. Schema hash ≠ model weights identity.
- Restore = full canonical snapshot + exact diff check (max diff must be 0.0); never arithmetic `-sigma*noise`. Exact verification must be memory-safe (chunked) on the 6 GB 1660S — without weakening the exact oracle.
- ES update: standardized one-point Gaussian; accumulate in **FP32**, cast/apply once, check the actually applied update. Equal rewards → logged no-op; NaN/Inf reward → reject (never coerce to 0). Aggregate in canonical candidate order, not arrival order. Infra failure is never task reward 0.
- Cross-machine regression compares noise hashes, sampled perturbed-weight hashes, all predictions, reward, and restore — reward alone is too coarse.

Baseline facts: model `Qwen/Qwen2.5-0.5B-Instruct`, pinned revision `7ae557604adf67be50417f59c2c2f167def9a775` (always pass `revision=`), FP16, 290 parameter tensors / 494,032,768 elements, sigma ≈ 1e-3 (provisional), 16-prompt exact-integer arithmetic smoke workload.

## Environment and commands

- Primary machine: this 5070 Ti box. Conda env `ai` (Python 3.12, torch 2.10+cu128) is known-good — do not modify it. `heteroes-match` (torch 2.13+cu132) matches the 1660S. The 1660S must run the **same Git commit**; don't develop separately there.
- Package is `src/`-layout setuptools (`pyproject.toml`, Python ≥ 3.12), installed editable:

```bash
pip install -e .
pytest                                   # testpaths = tests
pytest tests/noise/test_engine.py::test_name   # single test
HETEROES_QWEN_PATH=<dir of any Qwen2.5-0.5B checkpoint> pytest tests/model   # also runs the real-layout test S9 (otherwise skipped)
# HETEROES_QWEN_PATH=Qwen/Qwen2.5-0.5B-Instruct also works (HF cache). Expected: 117 passed (116 + 1 skipped without it)
```

- The 1660S copy lives at `~/projects/heteroes/hetero-es` (venv `~/projects/heteroes/.venv`, Python 3.14.4, NumPy 2.5.2, torch 2.13). SSH there only when the user asks for a specific action.

- Large weights (`*.safetensors`, `*.pt`, …) and `artifacts/**/checkpoints/` are gitignored; keep hashes/config/commands instead. Probe/regression JSON evidence goes under `artifacts/` and must not be overwritten.
- SSH is for setup/debug only; the runtime will use its own service protocol.
