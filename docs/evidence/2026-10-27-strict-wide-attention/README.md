# Wider short-context attention CTA: rejected for the primary goal

This standalone kernel uses four lanes per score, two 32-key value workers per channel, and a 64-key value
tile. For D=64, GQA repeat=7 and at most 128 keys it runs one 896-thread CTA per query/KV head, increasing
available warps while retaining the original FP32 products and adjacent-pair tree. The two value workers
produce the same aligned 32-key roots; pairing those roots reproduces the old pruned tree, including
ragged last tiles and signed zero. No multi-kernel key split or arithmetic approximation is introduced.

**57 tests pass** against both original CUDA and the independent CPU attention reference. They cover
key lengths 1/31/32/33/64/65/80/127/128, ragged packed masks, cancellation, signed zeros, subnormals, equal
scores and masked nonfinite flags. PTX/SASS audits pass. The initial fixture failed before execution because
it compiled before initializing a CUDA allocation/context; v2 retains an explicit context tensor. That
failure and the original source are preserved.

Matched graph-replayed controls use actual short-prompt lengths and synthetic tensors:

| Batch / decode step | Original µs | Wide µs |
| --- | ---: | ---: |
| 32 / 1 | 12.096 | 13.040 |
| 32 / 16 | 14.440 | 14.436 |
| 32 / 31 | 15.108 | 14.856 |
| 32 / 46 | 15.408 | 14.884 |
| 8 / 16 | 14.360 | 14.588 |
| 2 / 16 | 8.228 | 9.004 |

Early steps regress and the later gain is small. Reject for the primary short32 goal, without incurring
full-model integration complexity. The first benchmark requested an unsupported longer step and aborted;
its partial log is retained. The complete second benchmark chooses the last step whose longest prompt
fits 128 keys, rather than silently truncating the attention.

## What this does NOT show

No whole-generation improvement, arbitrary head/context support, other GPU/native, package, managed or
learning qualification is claimed. The kernel remains standalone and does not replace the selected runtime.
