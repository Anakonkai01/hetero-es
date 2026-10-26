# Exact compressed reciprocal lookup: correct, rejected for speed

The [design proof](harness/design.md) normalizes the input exponent, executes the original five separately
rounded Newton steps for every normalized mantissa, and losslessly encodes the result with integer chord
prediction plus exact nibble residuals. No approximate reciprocal is published. The full table is 32 MiB;
the compressed representation is **4,210,692 bytes**. Outside the original positive domain the GPU executes
the original function, preserving its error bits and NaN behavior.

CPU exhaustive comparison covers **1,671,934,059** admitted FP32 encodings; normalized table SHA-256 is
`c30d9363d614f4ac77143bc2e5e5f63c5ee14056e3b7d4eafd96e2c62ef4253a`. Four CPU tests also cover the independent
Torch reference, boundaries, rejected inputs and lossless reconstruction of all 2^23 mantissas. Three GPU
tests compare all 2^23 normalized mantissas, over one million other inputs, domain/nonfinite flags, and full
SiLU outputs. **All pass**; PTX/SASS audits remain enabled.

Warm-table CUDA-graph SiLU controls, in microseconds:

| Shape | Original Newton | Compressed lookup | Full lookup |
| --- | ---: | ---: | ---: |
| 32 × 4864 | 2.784 | 4.968 | 4.852 |
| 888 × 4864 | 53.360 | 84.300 | 95.712 |
| 32 × 2048 | 1.816 | 3.424 | 2.860 |

Both representations are slower even with warm tables. Reject at this operator gate; no decoder wiring,
new default or runtime module is selected. Full-table versus compressed results also show that removing
the integer codec does not make this particular access pattern competitive. The CPU/normalized tests
are retained because they establish exactness independently of this negative performance result.

The initial collection failure precedes the missing helper implementation. A later compression test red
snapshot is retained separately; its three original lookup tests remain unchanged in `test_lookup.py`,
and compression has its own final test file. Every measured GPU helper is kept at its measured source.

## What this does NOT show

No full-decoder, cold-cache, other-GPU, native, package or managed acceptance is claimed. These timings do
not rule out all lookup methods or all nonlinear kernels. No B22 arithmetic, historical recipe, ES update,
live lab process, driver or environment was changed by this standalone experiment.
