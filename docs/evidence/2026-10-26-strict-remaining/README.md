# Remaining decode attribution and unselected warp attention

Selected runtime is still B22 `b1ef257a`, with evidence HEAD `5bbaa110` at these measurements.
All new behavior is in scratch harnesses; runtime files remain unchanged.

External timing-event nodes surround nonoverlapping groups inside the captured Qwen step. This
extends the previous projection-only attribution to normalization, RoPE, cache stores, residuals,
activation, greedy selection and publication. Each reported sample is the final captured decode
step of a repeated generation, batch 32, context capacity 512. These event nodes perturb scheduling;
the measurements guide experiments and are not uninstrumented generation throughput.

| Final-step diagnostic | B22 short32 ms | B22 chat128 ms | Vendor FP16 chat128 ms |
| --- | ---: | ---: | ---: |
| Total | 6.214 | 7.916 | 5.874 |
| Attention | 1.116 | 2.806 | 2.811 |
| QKV | 0.583 | 0.585 | 0.284 |
| Attention output projection | 0.336 | 0.336 | 0.239 |
| Gate/up | 1.488 | 1.493 | 0.682 |
| Down | 0.993 | 0.996 | 0.440 |
| LM head | 0.701 | 0.703 | 0.358 |
| RMSNorm | 0.287 | 0.287 | 0.287 |
| RoPE | 0.171 | 0.171 | 0.182 |

This identifies attention as a worthwhile hypothesis on the longer trace, not a promise that an
isolated attention gain will transfer. Vendor FP16 projections are a different-arithmetic control.

The warp-attention prototype reads key channels together, reduces aligned 32-channel subtrees with
shuffles, and merges the same pruned tree. The `score` mode keeps the previous softmax/value path.
The `full` mode also distributes aligned numerator/value subtrees and shares one denominator
reciprocal. Every add/multiply, FTZ rule and polynomial constant is inherited unchanged. Loads/checks
still visit masked keys and values. Eight GPU tests pass against the independent CPU arithmetic:
dimensions 1/13/32/64/128/256, tails and GQA/packed ranges, masked NaN/Inf and masked score overflow.

Six operator cases compare prior/score/full with thirty calls per graph replay and ten samples per
variant in forward/reverse order. `attention-operators-5070ti-02.json` is the complete receipt:

| Case, batch 32 / heads 14 / dim 64 | Score ratio | Full ratio |
| --- | ---: | ---: |
| Decode, 32 keys | 1.177 | 1.150 |
| Decode, 128 keys | 1.231 | 1.306 |
| Decode, 256 keys | 1.207 | 1.275 |
| Decode, 512 keys | 1.445 | 1.540 |
| Prefill, 8 queries/keys per sequence | 1.843 | 1.314 |
| Prefill, 128 queries/keys per sequence | 1.115 | 1.029 |

Ratios are prior median latency divided by prototype latency. All output bits equal the prior
kernel. Attempt 01 failed because the benchmark dropped external layout tensor references while
graphs still held their addresses. Its source/log are preserved. Attempt 02 retains each layout
through every replay. This was a harness lifetime defect; selected runtime state retains its ranges.

The trained whole-generation ABCCBA pilot uses the same single FP16 Qwen model and exact token
equality for every repetition. It does not reproduce a compelling operator gain:

| Batch 32 | Prior token/s | Score token/s | Full token/s |
| --- | ---: | ---: | ---: |
| Short32 | 4,359.7 | 4,328.9 | 4,317.0 |
| Chat128 | 3,948.1 | 4,000.6 | 3,977.9 |

Stop this implementation rather than treating operator gains as a selected optimization. The
whole-path controls and raw graph diagnostics are separate evidence with separate limitations.
Use `PYTHONPATH=runtime/src:<folder>/harness`, isolated Python, explicit GPU opt-in and benchmark
`--gpu` to reproduce on matching local model paths.

## What this does NOT show

Selected performance gains, exclusive kernel attribution without profiling perturbation, cross-GPU
or native Windows acceptance, full error/stream/ownership qualification, quality or learning,
or near-vLLM performance. No remote GPU compute, push, merge or deployment occurred in this pilot.
