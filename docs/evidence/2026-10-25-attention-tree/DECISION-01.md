# Selected execution: source3fd704a5

Select power-of-two groups of8 for attention Q/K and probability/value reductions, with the same Tree over group
roots and a pruned final group. This preserves the exact reference expression tree for every admitted length.
`topology-proof-01.json` checks all1..4096 lengths with symbolic leaves, not rounded random samples. GPU tests also
cover carries, cancellation, negative zero, FTZ, partial groups, overflow and causally masked overflow.

Read the source carefully: decode already uses position+1 actual keys; max_context controls physical allocation.
A proposal to drop future/padding compute was not selected. Masked prefill arithmetic and its errors remain.

Compiler/resources do not alone select a variant. Unrolling Tree removes the baseline72-byte local frame, but
alone gives only2–3% B32 gains. The fastest group8 variant uses54 registers and144 local bytes on5070Ti, versus
54/72 on3060. Group16, explicit scalar leaves, named Tree slots and compact carry loops all pass numerical
checks but are slower overall. In particular, forcing zero local memory is not a throughput result.

ABBA same-process comparisons use one FP16 model and two compiled CUDA modules, never two weight copies.
Capture is released before changing the module route. Six timed observations per variant/batch are retained;
all token streams and final logit hashes match. These override receipts record supplemental CUDA-source hashes
and remain prototype evidence. Actual selected-source benchmarks and quality receipts are separate.

Three trained models match1848d57c and each other across5070Ti/3060 for parent, canonical7001± and restored
states, FP32 tree and both B14/B22. TinyLlama assets were downloaded at the pinned revision and verified byte
for byte against the local manifest, closing the former missing trained TinyLlama comparison.

The first resource-only probe lacked an active CUDA context and failed; retry02 explicitly allocates a CUDA
tensor first. Its original source is retained. This setup error is not a rejected numerical kernel.

## What this does NOT show

No general quality, all-GPU/all-version theorem, native installer/managed lifecycle qualification, default/recipe
activation or completion of M0–M6. Symbolic topology still depends on the implementation/compiler honoring the
listed primitives; instruction audits and physical tests remain required. No push/merge/deploy or learning run.
