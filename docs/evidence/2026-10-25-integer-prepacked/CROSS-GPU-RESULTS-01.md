# Current-source trained cross-GPU continuation

Source1848d57c: SmolLM2-360M and Qwen2.5-0.5B match between Linux5070Ti and WSL23060 for schema, pinned parent
and canonical7001± weight hashes, prefill hashes, tokens/text/rewards and exact restore. All four states and the
FP32 tree plus B14/B22 are compared separately; see cross-gpu-trained-comparison-01.json.

3060 B22 total output token/s at B1/B8/B32: Smol159.6/659.4/1246.8; Qwen154.7/577.2/1118.2.
The source's four-layout native Windows comparison remains a separate fixture result. Three local trained-model
profiles now put projections at58–78% of B32 CUDA event time and attention at16–30%; profiler event sums include
prefill/decode and overhead, and are not wall-time attribution or a throughput result.

## What this does NOT show

No trained TinyLlama cross-GPU result, general quality/heterogeneous theorem, native installer/managed acceptance
or completion of M0–M6. No push/merge/deploy or learning. Existing receipts, including failed/rejected prototypes,
are unchanged. Native source and fixture checks do not prove the entire managed product lifecycle.
