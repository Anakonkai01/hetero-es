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

What has worked in practice (steps 4a–4c, 05/10): the AI writes the tests first (independent oracle written by hand from the contract, plus a test that the test data can tell the right answer from the known wrong one); the owner writes the code from hints; then the AI runs the tests and a **mutation check on a scratch copy of `src`** (never on the repo): deliberately break the code and confirm a test turns red; a mutant that stays green is either an equivalent mutant (say so) or a gap in the tests (add a test). The owner chooses names (adapt the tests to them) and has the final say on decisions: state the trade-off once, then follow. Commits are made by the AI only when the owner asks, and without a Co-Authored-By line.

## Implementation order — do not reorder casually

1. ParameterSchema / numerical contract → 2. production CanonicalNoiseEngine → 3. unit/contract tests → 4. route all perturb/reconstruct/update paths through the one engine → 5. FP32 update accumulation + notebook numerical debt → 6. local regression → 7. cross-machine same-candidate regression (5070 Ti vs 1660S) → 8. freeze candidate/noise manifest v1 → 9. commit + evidence + STATUS update.

**The gate (steps 1 to 9) was closed on 2026-10-06 for one candidate on the 5070 Ti and the 1660S (STATUS 0.0, step 9).** Only after that gate: minimal worker/coordinator HTTP, one remote candidate, frozen two-node generation, SQLite ledger, fake-worker fault tests, C1/C2, sync experiments. **No FastAPI/scheduling/DB/Docker work before the cross-machine same-candidate regression passes.** Docs planned for this phase: `docs/architecture.md`, `docs/numerical-contract.md`, `docs/adr/ADR-001-canonical-noise-engine.md` — only these, not the full docs tree.

Modules (implemented): `src/heteroes/model/schema.py` (ParameterSchema, `resolve_tensors`, `SchemaMismatchError`; see `docs/numerical-contract.md` §2 status note), `src/heteroes/noise/contracts.py` (`ChunkNoiseAddress`, `ParameterNoiseAddress`), `src/heteroes/noise/engine.py` (CanonicalNoiseEngine v1), `src/heteroes/es/perturb.py` (`perturb_parameter_`, `perturb_model_`), `src/heteroes/es/snapshot.py` (`take_snapshot`, `diff_from_snapshot`, `restore_from_snapshot_`, `RestoreError`), `src/heteroes/es/checks.py` (shared input checks), `src/heteroes/es/update.py` (`UpdateReport`, `standardize_rewards`, `apply_es_update_`; written by the owner and finished on 05/10 evening), `src/heteroes/eval/workload.py` (the 16-prompt workload, reward, `workload_hash`), `src/heteroes/eval/generate.py` (`generate_answer`, `evaluate_model`), `src/heteroes/eval/candidate.py` (`run_candidate`, `model_weights_sha256`; step 6, 05/10 night). `scripts/run_one_candidate.py` runs one candidate end to end and writes a JSON record of format 2 (evidence in `artifacts/regression/2026-10-05-one-candidate/`, format 1); `scripts/compare_candidate_records.py` compares two records. Step 8 added `src/heteroes/canonical.py` (the ONE serialization for every hash), `src/heteroes/noise/selftest.py` (noise fingerprint and self-test) and `src/heteroes/manifest.py` (`Recipe`, `CandidateDescriptor`, `derive_seed`; contract §12). Steps 5 to 7 are checked on both machines: the same candidate (seed 0, sigma 1e-3) gives identical weights and identical outputs on the 5070 Ti and the 1660S, 404 tests pass on both (evidence in `artifacts/regression/2026-10-06-cross-machine-one-candidate/`; see STATUS 0.0 and `TODO.md`). Tests mirror packages under `tests/{es,model,noise}/`. `scripts/o2_cross_gpu_check.py` is a self-contained cross-GPU check (it contains a *copy* of the engine so it can run on Colab/Kaggle; the package engine is the only production implementation).

Decided so far: O1 (2026-10-01) — production schema hash includes aliases and `schema_version`; O3 (2026-10-01) — restore oracle is bitwise; O2 (2026-10-03) — perturbation arithmetic is option (c), see below; O4 (2026-10-05) — the update uses the canonical FP16 epsilon upcast to FP32; eta = 1e-9 (2026-10-05); O5 (2026-10-06) — seeds are explicit in the candidate descriptor, `0 <= seed < 2^53`; O6 (2026-10-06) — no NumPy version is pinned, the noise behaviour is pinned by a fingerprint and a self-test; manifest v1 is frozen (contract §12). No open O-decision is left (see contract §11). Code-level TODOs live in `src/` (`grep -rn TODO src/`).

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

# Real-model tests need the ORIGINAL pinned checkpoint (an ES-modified one gives different hashes). On the 5070 Ti box it is in the HF cache:
SNAP=~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775
HETEROES_QWEN_PINNED_PATH=$SNAP HETEROES_QWEN_PATH=$SNAP pytest tests      # about 50 s on the GPU (measured 05/10 evening)
# expected (5070 Ti, 06/10): 535 passed with the env vars (about 107 s); 521 passed and 14 skipped without them. (On the 1660S 404 passed before step 8, 471 s.)
# One candidate end to end: python scripts/run_one_candidate.py --model-path $SNAP --seed 0 --sigma 1e-3 --repeat 2 --output <new file>
```

- The 1660S copy lives at `~/projects/heteroes/hetero-es` (venv `~/projects/heteroes/.venv`, Python 3.14.4, NumPy 2.5.2, torch 2.13). SSH there only when the user asks for a specific action; on 2026-10-06 the user authorized SSH for step 7 (password login, nothing stored). Unpushed commits go there as a `git bundle` copied with `scp`.

- Large weights (`*.safetensors`, `*.pt`, …) and `artifacts/**/checkpoints/` are gitignored; keep hashes/config/commands instead. Probe/regression JSON evidence goes under `artifacts/` and must not be overwritten.
- SSH is for setup/debug only; the runtime will use its own service protocol.
