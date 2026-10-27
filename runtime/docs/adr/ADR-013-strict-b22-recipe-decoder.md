# ADR-013 — The strict B22 decoder as a Recipe v3 decoder

Status: accepted by the owner's plan of 2026-10-27 ("B22 is the default for new GPU runs after its integration gates").
Builds on [ADR-012](ADR-012-single-model-strict-inference.md) and [ADR-008](ADR-008-recipe-v3-and-extensible-experiments.md).

## Decision

1. A Recipe v3 document selects the strict backend with `evaluation.decoder = "strict_b22_v1"`. It is a new value of the
   existing field, like `hf_fp32_cpu_guard_v1`: every existing document keeps its bytes and hash, and Recipe v1/v2
   vocabularies are not extended.
2. The identity of `strict_b22_v1` is the arithmetic, not the kernels: B22 row-scaled integer projections
   (`integer-projection-v1.md`), strict FP32 nonlinearities, attention and greedy selection (`strict-decoder-v1.md`).
   Execution routes that give the same bits (tile/stream schedules, split K, TMA operands, K/V stage sizes, request-sized
   KV slots) are not part of the recipe; they are recorded per device in kernel identities and receipts.
3. `strict_b22_v1` requires `evalDtype = "float16"`: the decoder reads the live FP16 weights in place. No FP32 shadow and
   no second weight set exists (D1). The FP16 perturb publication, canonical noise, update order and exact CPU-snapshot
   restore are unchanged.
4. Rows are computed independently (row-scaled projections, per-row attention and selection), so the output of a row does
   not depend on its chunk neighbours. `evaluation.chunk(s)` of a strict recipe may be any of 1, 2, 4, 8, 16, 32 or 64.
5. Generation settings come from the pinned generation config (`generationConfigSha256`): greedy, its EOS ids and its
   repetition penalty. Sampling, beams and other processors are refused before decoding, never approximated.
6. Failures are never rewards. A request over the decoder's explicit memory budget is `OUT_OF_MEMORY` (the executor's
   existing smaller-chunk retry applies). A transport timeout (error bit 8) is an infrastructure failure. A nonfinite or
   out-of-domain value in the strict arithmetic is a property of the candidate on every device; it is reported as a
   candidate failure (`OTHER`) with its message, not coerced to reward 0. Changing that into a scored outcome would
   need a ledger change, which the frozen numerical contract does not allow without a separate owner decision.
7. Unsupported model graphs or configurations are refused when the worker loads the recipe; nothing falls back to
   ordinary vendor kernels under this identity.
8. After the M4 qualification gates pass, new GPU runs created by the lab and the SDK default to `strict_b22_v1`.
   Existing runs, templates already saved by researchers and replays keep their own decoder.

## Consequences

Qualification, reference and profiling caches that are keyed by the recipe/document hash separate strict and
historical evaluation automatically. Results produced under `strict_b22_v1` are expected to be token-identical across
the supported NVIDIA GPUs and operating systems; the acceptance gates (`scripts/accept.py`) record where this has been
checked and where it has not. A different arithmetic (for example B14 or mixed precision) needs its own decoder value.

## Amendment 2026-10-27 (M4: D1 and the default)

Found while integrating: the coordinator validates and exports a Recipe v3 run (`v3/tracker.py`) with the run's own
decoder, so a strict run's coordinator needs a GPU, and that GPU holds the coordinator's live model for the whole run.

1. **D1 for strict runs.** The lab refuses (at creation, and again at scheduling and for elastic joins) a strict run
   whose coordinator is a CPU-only coordinator ("needs a GPU coordinator"), or whose coordinator device or physical GPU
   is also one of its workers ("one weight set per GPU"). The worker's audits run in its single executor; the export
   reload happens only after the live model and its strict engine have left the GPU (`Tracker._release_device`).
   Earlier recipes keep their layouts and their FP32 evaluation shadow; D1 is promised for `strict_b22_v1` only.
2. **Consequence.** A strict lab run needs two GPUs (one coordinates, the others work); a single-GPU lab keeps the
   earlier decoders. Sharing one runtime between coordinator validation and a worker on the same GPU (or delegating
   validation to the workers) is the way to lift this and is not built.
3. **Default.** The lab form selects `strict_b22_v1` for a new Recipe v3 run; a saved run, a template and a replay keep
   their decoder. The SDK keeps `ESConfig(decoder="hf_generate", eval_dtype="float32")` as its default: an `ESConfig`
   recipe does not depend on the device it later runs on, and changing the dataclass default would silently change the
   recipe of every existing script. A strict SDK run states `decoder="strict_b22_v1", eval_dtype="float16"`; it reaches
   the lab with `evalDtype` and is qualified for the strict decoder (`sdk_lab.Lab.qualify(decoder=...)`).
