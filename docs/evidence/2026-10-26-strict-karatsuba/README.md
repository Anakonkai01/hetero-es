# Unselected B13 radix-128 product decomposition

Runtime base `b1ef257a`, receipt HEAD at entry `01e13637`. This is scratch-only NEW projection
arithmetic: row maximum exponent e, integer RNE scale `2**(e-12)`, operand bound ±8192, exact integer
dot, then the existing scaled-integer FP32 RNE/signed-FTZ encoder and strict bias add. It is not B22.
Original FP16 weights stay primary; quantization happens inside bounded tiles, not a model shadow.

For each admitted integer q, set `low=((q+64) mod 128)-64`, `high=(q-low)/128`. Both limbs and
`low+high` fit signed bytes. Let p0=dot(a0,b0), p2=dot(a1,b1), ps=dot(a0+a1,b0+b1). Then the exact
dot is `p0 + 128*(ps-p0-p2) + 16384*p2`: three MMA products instead of the four products in the
same-arithmetic schoolbook control or nine in B22. Signed byte-product accumulators remain within
int32 at width 32768; reconstruction uses int64. The independent CPU oracle uses rational row
quantization and a direct integer dot, without the GPU limb decomposition.

Five tests pass on local 5070 Ti: exhaustive admitted scalar limb bounds/reconstruction, RNE ties,
independent CPU/GPU outputs for both implementations, odd tails/offsets/bias/splits, live weight
change/restore, maximum width and all-zero rows. No remote, native, decoder or quality acceptance
has been run for B13. No mutation check has been run for this prototype yet.

Initial implementation stores low/high/sum activation planes and uses weighted reconstruction.
The first five-shape pilot shows that three products do not automatically improve speed. The
final implementation keeps only low/high planes, forms byte sums in registers without cross-byte
carries, and reconstructs through power-of-two multiplications. One intermediate version incorrectly
modified shared weight-register operands again for the second M group; the existing 19-row oracle
test catches it. Attempt 02 and its failed log remain. The final version computes weight sums once
per K tile and passes `gpu-5070ti-03.log`.

Operator measurements use one shared FP16 weight tensor per shape, thirty calls per graph replay,
forward/reverse order and ten event samples per variant. Final full outputs of schoolbook/Karatsuba
match each other, with sampled outputs checked against their independent CPU oracle. Ratios are
B22 median latency divided by prototype latency, not a whole-model speedup.

| Shape (M,K,N) | Final B13 schoolbook ratio | Final B13 Karatsuba ratio |
| --- | ---: | ---: |
| 32,896,128 | 1.001 | 1.050 |
| 32,896,896 | 1.222 | 1.189 |
| 32,896,4864 | 1.223 | 1.187 |
| 32,4864,896 | 1.340 | 1.334 |
| 32,2048,5632 | 1.265 | 1.311 |

The final three-product version is not consistently faster than its four-product control. There
is a modest operator lead over B22 on larger shapes, but less quantization precision and all decoder,
quality, candidate, resource, heterogeneous/native and mutation gates remain. No B13 decoder adapter
has been implemented; a proposed B13-body/B22-head composition was only discussed, not executed.

The final harness and both earlier kernel snapshots are retained. Kernel JSON identities pin the
prototype/parent sources and compiler audits. Reproduce with the isolated Python and
`PYTHONPATH=runtime/src:<folder>/harness`, explicit GPU opt-in and benchmark `--gpu`.

## What this does NOT show

A selected runtime speedup, B22-equivalent arithmetic, whole-model throughput, quality or learning,
cross-GPU/native Windows acceptance, complete stream/resource/ownership qualification, or near-vLLM
performance. No push, merge or deployment occurred. Further experiments were stopped for session handoff.
