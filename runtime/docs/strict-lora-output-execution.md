# Output-parallel execution of the strict LoRA finish

This is a scheduling change to the existing strict FP32 adapter arithmetic, not a new precision, quantizer,
adapter model or recipe. The frozen integer base, first adapter product and FP16 storage are unchanged.
The full approved M0-M6 plan and managed qualification gates remain open.

## Arithmetic argument

The preceding warp implementation gives one output column to a warp. Lane `k` contains
`mul_rn(flush(middle[row,k]), widen(B[column,k]))` when `k < rank`, otherwise negative zero. XOR exchanges at
offsets 1, 2, 4, 8 and 16 give lane zero the canonical adjacent-pair tree over 32 leaves. Every multiply/add
has a separate FP32 round-to-nearest boundary and the declared signed FTZ behavior. Contraction is forbidden.

The output-parallel implementation assigns one output element to each thread. Let `P` be the next power of
two at least as large as the rank. Its register array holds exactly the first `P` leaves of that warp tree,
including negative-zero leaves between rank and `P`. At offset `s`, register `j` at every multiple of `2s`
receives the same `add_rn` of the same two child subtrees as lane zero's corresponding subtree in the warp
implementation. Induction over offsets 1 through `P/2` therefore gives exactly the same `P`-leaf result.

The remaining complete subtrees contain only negative zero. Their pairwise sums are negative zero, so the
kernel explicitly appends `add_rn(value, -0.0)` for `P`, `2P`, and so on up to 16. This reproduces the full
32-leaf root even for signed zero; it does not reassociate any live products. Rank 1 and odd ranks use the
same construction. NaN/overflow propagation is checked through the final nonfinite error flag.

The existing strict scale follows the root. A zero scaled delta selects the original base bits without an
addition; a nonzero delta performs the existing strict add. The base and result nonfinite checks remain.
There are no floating atomics, Tensor Core FP16 products, FMA contractions, runtime data-dependent precision
changes, or ordinary-vendor fallback. The compiled PTX/SASS audits still reject forbidden arithmetic.

## Execution and admission

The public operator retains `execution="warp"` as a strict control and exposes `execution="output"` for the
new schedule. A block has 256 threads; its output tile is `256 / row_tile`, and its row tile is 1, 2, 4 or 8.
Each thread writes one independent output, with tails masked before reading inputs. No shared transpose or
block barrier is needed by the output schedule. Both explicit schedules support ranks 1-32.

The frozen CUDA decoder selects output execution for ranks <=16 and retains warp execution above 16.
The decision follows measured dimension/rank behavior on SM120 and SM86. In particular, some rank-32 shapes
on SM86 regress slightly with output execution; those measurements are retained. There is no model-name or
GPU-name dispatch. Changing row/output tiling cannot change a live product's floating reduction tree.

The decoder rejects rank >32 before CUDA graph setup. The independent eager reference can still represent
higher ranks; that does not make them admitted CUDA configurations.

## Evidence and limits

The tests compare odd ranks, tails, all explicit row tiles, cancellation, negative zero, FTZ input endpoints,
nonfinite errors and captured replay against the CPU reference and retained warp implementation. Scratch
mutations test the scale, tree, input FTZ, zero select and admission boundary. Real-model comparisons use
the same pinned on-disk frozen files, exact adapter files, parent manifests, prompts and candidate descriptors.

[The measured continuation](../../docs/evidence/2026-10-25-frozen-subwarp-perf/README.md) records operator
sweeps, matched model timings and exact before/after and cross-architecture scope. CUDA event operator gains
are not end-to-end speedups. General base-quantization/trained-adapter quality, full lifecycle memory, native
Windows and managed/default activation require their own evidence; `hardwareQualified` remains false.
