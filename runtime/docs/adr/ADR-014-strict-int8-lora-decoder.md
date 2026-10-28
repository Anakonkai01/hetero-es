# ADR-014 — `strict_int8_lora_v1`: a frozen int8 base with FP16 LoRA adapters (M6)

Status: accepted under the owner's plan of 2026-10-27 ("M6 uses the existing int8 per-row frozen format + LoRA").
Builds on [ADR-013](ADR-013-strict-b22-recipe-decoder.md) and the frozen-int8 receipts of 2026-10-25
(`docs/evidence/2026-10-25-frozen-int8-oracle`, `-integration`).

## Decision

1. A Recipe v3 document selects the frozen int8 base with `evaluation.decoder = "strict_int8_lora_v1"`. It is a new
   decoder value because its arithmetic differs from `strict_b22_v1`: the LoRA target projections use the pinned
   per-output-row int8 rows and their exact three-limb product, the adapter delta uses the strict FP32 operator
   contract, and the other projections (embeddings, LM head) use the strict decoder graph's own arithmetic. Every
   existing document keeps its bytes.
2. The weight space is LoRA (`rank` at most 32, `alpha`, `targetModules`, `initialAdapterSha256`) plus
   `frozenBaseSha256`: the canonical hash of `{projection name: int8 artifact digest}`. The rows are quantized from the
   pinned FP16 files on the host, so every machine computes the same bytes; a worker that computes another hash refuses
   the recipe. `frozenBaseSha256` exists only with this decoder, and this decoder only with it.
3. Only `lora_A`/`lora_B` are parameters. Perturbation, update, the exact CPU-snapshot restore and the published
   weights cover the adapters only; the int8 rows, scales and FP16 biases are buffers sealed by their digests, checked
   by the CUDA graph at each request. The FP16 weights of the replaced projections are freed when the base is frozen,
   so no dequantized copy remains (the FP16 model exists once, while it is loaded and frozen).
4. Like `strict_b22_v1`: FP16 evaluation, any chunk of 1–64, greedy decoding from the pinned generation config, the
   strict first-mismatch audit stop, failures never coerced to rewards.
5. Not offered by the lab yet (refused with a reason by `validate_options` and the SDK's lab bridge): it runs with
   `python -m heteroes.v3 run|serve|worker` and the SDK. Coordinator export of a frozen base is refused explicitly.

## Consequences

The lab needs qualification references for this decoder, a form option and an export format before it can offer it.
D10 restore recovery reloads FP16 base weights from the files; the frozen int8 buffers are not reloaded but are
verified against their digests by the graph before every request.
