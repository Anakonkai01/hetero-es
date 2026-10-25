# B22 raw weight prefetch

The selected execution policy reads the next live FP16 weight tile while the current tile is
quantized and multiplied. It preserves the row-scaled integer contract: the same `quant_half`,
signed radix packing, integer MMA products, reconstruction, final rounding and error checks.
The single-row SIMT kernel is unchanged. No global weight transform or persistent weight copy
is introduced.

Each thread owns two sixteen-byte slots in explicitly sixteen-byte-aligned shared memory. Its two eight-byte copies load four
adjacent halves each. Eight-byte copies require an eight-byte-aligned base and a width divisible
by four; tile starts and lane offsets preserve that alignment. Otherwise guarded scalar reads
populate the same slots. Missing columns or K elements become positive zero. Zero-length async
copies use the valid base pointer and zero-fill the destination, avoiding out-of-range pointers.

Before processing tile `start`, the thread waits for its outstanding copy group and reads that
slot into registers. It then issues the next tile at `start + SPLIT_K*32` into the other slot.
Thus every consumed half has exactly the scalar tile's address and value. Shared slots have
disjoint ownership; each producer and consumer is the same thread, so no cross-thread barrier
is required. The final wait drains the last lookahead, including split partitions with no live
tile, before storage can be reused. Scratch is 4096 bytes per four-warp CTA or 8192 per eight-warp
CTA, independent of model size.

`weight_load="prefetch2"` explicitly selects this implementation. `"scalar"` and `"paired"`
retain their guarded controls. `"auto"` selects prefetch2 for B22 on measured SM86 and SM120;
B14 and other architectures retain scalar reads. Requested and effective policies and distinct
compiled names are recorded in the existing identities. Decoder configuration checks freeze
the requested policy. This is an execution choice within B22, not new arithmetic or a claim
that unmeasured architectures will improve.

Numerical, instruction, model/candidate and performance receipts are recorded separately in
[`2026-10-26-strict-prefetch`](../../docs/evidence/2026-10-26-strict-prefetch/README.md).
They do not establish universal model quality or enable the managed execution path.
