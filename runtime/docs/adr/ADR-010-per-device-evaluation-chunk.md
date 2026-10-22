# ADR-010: Per-device evaluation chunk

Status: accepted by the owner (2026-10-22, "Chunk theo từng máy, ghi vào sổ"), implementation in fix wave 2.

## Context

A v3 recipe pins one `evaluation.chunk` (prompts per `generate()` call) for every device, because a different batch
shape can change a generated token (measured: 1 GSM8K text in 768) and every candidate's completions are audited by
re-running them on another GPU and comparing the SHA-256 of the texts. So the smallest card decides the chunk for all:
the 6 GB 1660S caps it at 32, and a 16 GB RTX 5070 Ti gains nothing from its memory. `EXACT_CHUNKS` lists the chunks whose
texts were measured equal across GPU models at a fixed chunk (FP32: 16, 32, 64).

## Decision

1. A recipe may declare `evaluation.chunks`: the allowed chunks, ascending, each in `EXACT_CHUNKS[evalDtype]`, and
   containing `evaluation.chunk` (which stays the default and the chunk of the coordinator's own validation). Without
   `chunks` a recipe means exactly what it meant before (one chunk), and its hash is unchanged.
2. A worker evaluates its own candidates with the largest allowed chunk its device may use (`maxChunk` of the worker's
   start command, from the device profile or the owner's VRAM limit; absent: the recipe's `chunk`).
3. **The chunk is part of the result.** A completion result carries `chunk`; the ledger stores it with the completion
   (`completion_chunk`). A result whose chunk is not in the recipe's allowed set is refused.
4. **Audits re-run the candidate at the original chunk.** The audit lease carries it; a worker that may not use that
   chunk is not given that audit (it would fail for memory, not for exactness).
5. Regeneration (`verify_managed_run.py --regenerate`) uses each candidate's recorded chunk.
6. The weight update is unchanged: it uses the rewards, and the rewards come from the recorded completions.

## Consequences

- Rewards of one generation may come from different chunks. That is a property of the recorded run, not a source of
  silent divergence: every number can still be reproduced exactly, because the chunk is recorded beside the texts.
- A chunk enters `EXACT_CHUNKS` only after a cross-GPU probe at that chunk (RUNTIME-TODO `chunk-128`).
- Older coordinators and workers: a recipe with `chunks` requires the new runtime (the recipe validator of an old one
  refuses the unknown key); a recipe without it runs everywhere.
