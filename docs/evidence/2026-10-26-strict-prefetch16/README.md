# Unselected 16-byte raw weight copies

Runtime base `b1ef257a`. This scratch execution changes the next-tile load from two eight-byte copies
per lane to one sixteen-byte copy. Four neighboring lanes redistribute the raw halves through shared
memory. Per-thread async waits followed by full-warp synchronization order cross-lane reads and later
reuse; a final wait/barrier drains outstanding lookahead. Quantization, MMA, sums and output arithmetic
remain B14/B22. The primary FP16 weights are shared with the control; no transformed model cache exists.

Two parameterized GPU tests pass on each host, covering B14/B22 tails, offset bases, split partitions
including empty partitions, row tiles and four/eight warps against the independent CPU oracle. The
fourteen-shape operator pilot uses a graph containing thirty calls per replay to reduce host submission
gaps; raw timings and identities remain. Operator gains do not establish full-model performance.

Trained Qwen pilot: same eight-prompt pool, 32 outputs, context 512, ABBA and ten host-wall samples per
variant. The selected eight-byte implementation is the explicit control. All generated tokens agree.

| GPU / batch | Selected token/s | Prototype token/s | Gain |
| --- | ---: | ---: | ---: |
| 5070 Ti / 1 | 276.2 | 276.8 | 0.22% |
| 5070 Ti / 8 | 1870.1 | 1926.5 | 3.02% |
| 5070 Ti / 32 | 4360.1 | 4563.2 | 4.66% |
| 3060 / 1 | 176.9 | 176.0 | -0.50% |
| 3060 / 8 | 783.2 | 807.5 | 3.10% |
| 3060 / 32 | 1327.0 | 1447.4 | 9.08% |

The prototype remains unselected pending the three-model, canonical candidate, resource/native and
mutation gates. Its scratch source is retained for later combination with other measured improvements.
The selected production runtime remains `b1ef257a`.

## What this does NOT show

Selected optimization, all-model/native acceptance, broad quality, arbitrary cross-GPU candidate
parity, near-vLLM speed, managed activation or learning. No push, merge or deployment occurred.
