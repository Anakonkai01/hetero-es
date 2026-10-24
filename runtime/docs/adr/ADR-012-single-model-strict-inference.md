# ADR-012 — One model per GPU and a versioned strict inference backend

Status: owner decisions accepted on 2026-10-24; implementation and hardware acceptance in progress.
This ADR records the owner's Q1–Q11 answers and subsequent authorization to start autonomous implementation.
It does not claim that a new inference backend already exists or has passed cross-device acceptance.

## Decision

- HeteroES-managed roles share at most one full set of inference weights on each GPU. This includes worker,
  coordinator validation, profiling and independent export reload, across managed processes. Bounded tile/slab
  workspace is allowed. A CPU parent snapshot of the trainable schema remains the exact-restore oracle.
- The new backend must produce the same token IDs/text and reward for the same candidate and inputs across
  heterogeneous supported NVIDIA devices. Identical intermediate logits are not an owner requirement.
  Re-scoring equality also requires a deterministic scorer; arbitrary Python code is not certified by a source hash.
- A new versioned recipe/backend may differ from historical FP32 evaluation. Historical documents, hashes,
  canonical noise, perturb/update ordering and recorded replay retain their meaning.
- Start with the pinned Qwen2.5-0.5B-Instruct revision and full/subset FP16 ES; expand by model-family/operator
  coverage. Quantized frozen bases with floating LoRA adapters follow. Full quantized-weight ES is separate research.
- Target heterogeneous NVIDIA GPUs on Linux and native Windows. AMD/Intel are outside the current implementation scope.
- A strict audit text mismatch stops before the next update, preserving committed evidence and identifying neither
  participant as the correct one by assumption. Incomplete audit coverage remains separately visible.
- A restore-only fault may trigger one clean worker recovery per worker/run. Stop locally, persist the fault,
  reload the canonical parent, verify identity/self-tests/exact restore and probation, then rejoin at a generation
  boundary. Repeated restore faults or inference mismatches require operator intervention. The allowance survives restart.
- Stage/progress watchdogs complement finite, explicitly configured researcher/operator hard caps. A heartbeat
  proves connectivity, not useful computation progress. The one automatic coordinator recovery limit is unchanged.

## Why a dtype switch is insufficient

`EvalModel` currently keeps a full FP32 deepcopy of the live FP16 model. Removing the shadow eliminates duplicated
weights, but historical FP16 experiments already include cross-GPU text and reward differences. Standard deterministic
flags, a fixed seed, quantized storage or a finite passing corpus do not establish an all-input numerical guarantee.

A strict backend needs a complete operator contract: casts, reduction order, FMA/contraction, normalization,
RoPE constants, attention/softmax, nonlinearities, cache, masks, processors, argmax ties and stop/padding rules.
Unsupported operations/configurations cannot silently fall back to ordinary vendor kernels under the strict identity.
FP16 storage with bounded FP32 tile computation and specified fixed-point operations are candidates for the feasibility
stage; neither is selected or accepted merely by this ADR.

## Acceptance gates

1. Inventory the full supported graph/configuration and define an independent numerical reference.
2. Check operator known answers, boundary values, odd shapes, long reductions, masks and ties. Explain the operation
   sequence and compiler/hardware assumptions; tests supplement that argument rather than replacing it.
3. Check complete parent/perturbed candidate token streams across devices, batches, prefill/decode and supported OSs.
4. Check lifecycle allocation peaks, perturb/restore/replay, failures, validation/export and source/native packaging.
5. Measure resources, throughput and end-to-end generation cost before promoting a default or choosing performance limits.

The prototype may fail a gate. Preserve counterexamples and report the remaining work instead of weakening exactness
or declaring universal support. Record CPU fixtures, numerical replay, inference regeneration and GPU/native Windows
acceptance separately. The new backend/reference identity must namespace qualification and profiling caches.

## Implementation and authorization boundaries

The owner approved autonomous implementation and explicitly authorized GPU experiments and SSH to `3060-thao`.
This does not change device approval/revocation or authorize a lab deployment. Use explicit GPU opt-ins, keep the
existing `ai` environment unchanged and preserve host usability/oomd and the accepted data-retention policy.
Keep credentials out of commands/logs/documents/commits. Record unreachable hardware as an acceptance limitation.

The initial work adds opt-in host phase traces and storage inventory, a CPU reference/probe and meaningful regression
tests. Delivery/scorer/usage concurrency and recovery I/O fixes can progress independently once reproduced by tests.
Do not run the old two-model GPU path just to obtain a fresh baseline in violation of the accepted resource contract.
