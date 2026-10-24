# Experimental single-model numerical reference

This document specifies the candidate arithmetic behind ADR-012. The implementation is deliberately slow and is
**not a production backend or a qualified recipe**. Existing recipes, FP32 evaluation, noise, publication, update
order and historical replay retain their current identities. Runtime integration and default changes remain gated.

Source: `eval/reference_ops.py`, `eval/qwen2_reference.py`. Operator identity:
`pairwise_f32_reference_v1_experimental`; graph identity: `qwen2_pairwise_f32_reference_v1_experimental`.
Each instance fingerprints the source bytes, graph dimensions, numerical constants, RoPE frequency bit patterns,
context limit and fixture flag. A fixture receipt cannot certify the real-model configuration.

## Arithmetic sequence

All arithmetic below uses IEEE binary32 round-to-nearest, ties-to-even basic operations. Each addition and
multiplication is a separate eager operation. At every input and result boundary, binary32 subnormals become signed
zero by integer bit selection; nonfinite values fail explicitly. Unary negation and selection do not perform a sum.
There is no vendor GEMM, fused multiply-add, vendor transcendental, unspecified floating reduction or automatic
fallback in this reference. Compiling/fusing it without checking the resulting instruction sequence is unsupported.

For an ordered vector of length N, the reduction replaces adjacent pairs with their rounded sums. An unpaired final
element is carried unchanged. Repeat until one element remains. Changing the row/output execution tile does not
change the product or reduction order within an output. A linear projection widens at most `output_tile` rows of
the FP16 weight matrix at a time (default 32), multiplies each FP32 activation by the corresponding widened weight,
reduces along the input dimension with that tree, and adds the bias in a separate rounded operation. Live model
weights remain FP16. Activations and call-local KV caches are FP32; these are distinct from a second set of weights.

The reciprocal starts from integer bits `0x7ef311c3 - bits(x)`, followed by five explicitly rounded Newton steps
`r = r * (2 - x*r)`. Reciprocal square root starts from `0x5f3759df - (bits(x) >> 1)` and uses six steps
`r = (0.5*r) * (3 - x*(r*r))`, with the shown parentheses and separate multiply/add operations. Both accept only
the declared positive interval [1e-30, 1e30]. This is a specified approximation, not a vendor correctly rounded divide.

Exponential uses a fixed base-two range reduction, two split ln(2) constants and a fixed degree-eight polynomial;
the power-of-two scale is constructed from exponent bits. Inputs below -80 produce positive zero, and inputs above
80 fail. Sine/cosine use three split pi/2 constants, fixed polynomials and integer quadrant selection on
[-32768, 32768]. The exact coefficients and ordering are source-hashed. SiLU uses `exp(-abs(x))` with sign-dependent
selection to avoid overflow. RMSNorm uses the fixed tree for the mean square and the specified inverse square root.
Softmax selects the masked maximum, applies the specified exponential, reduces nonnegative numerators with the fixed
tree and applies the specified reciprocal. Fully masked rows produce zeros. An unsupported domain fails the candidate.

## Qwen graph and generation

The initial real-model scope is the pinned Qwen2.5-0.5B-Instruct architecture: hidden size 896, intermediate 4864,
24 layers, 14 query heads, two KV heads, head dimension 64, vocabulary 151936, tied embedding/output head, SiLU,
full causal attention and default RoPE theta 1e6. A separate explicit fixture flag permits small test configurations.
Training mode, other RoPE variants, sliding attention, untied heads, non-FP16 parameters and mixed devices fail.
The reference context limit is explicit and at most 32768; the probe currently uses 256.

RoPE frequencies are constructed on CPU using Decimal precision 80 and published as FP32 bit patterns. The attention
scale uses the same local precision. Neither depends on the caller's Decimal context. Their published values are in
the backend identity. The graph implements embeddings, RMSNorm, Q/K/V projections, GQA, RoPE, causal attention,
output projection, residuals, normalized gated MLP, final normalization and tied vocabulary projection directly.
The HF model's forward/generate methods are not called. KV caches are local to a generation call and never survive
candidate mutation. The lower-level `forward_tokens` cache API validates structure, not model lineage.

Only greedy generation is supported. The reference validates every input token, strips left padding, then evaluates
each packed prompt separately so batch/padding shape cannot move the reduction tree of another prompt. This serial
execution is an oracle choice, not a throughput target. Repetition penalty is the only supported logits processor;
unknown options, sampling, beams, invalid masks and an over-budget context fail before forward computation. An exact
logit tie selects the lowest token ID. EOS tokens end the corresponding row; completed rows are padded in the returned
batch. A deterministic scorer is still required separately for reward identity.

## Reasoning and remaining gates

Given identical published inputs/constants and correctly rounded primitive operations, the fixed finite instruction
sequence determines each intermediate value. That is the basis for cross-device equality; setting a random seed or
passing a finite corpus is insufficient. Eager PyTorch/compiler/CUDA behavior still needs checking against those
assumptions on every supported build. Generated kernels must preserve the tree, FTZ boundaries, rounding and error
behavior. Unsupported hardware/software cannot acquire a strict qualification from a matching model hash alone.
See [NVIDIA floating-point guidance](https://docs.nvidia.com/cuda/floating-point/index.html).

Independent CPU tests cover scalar rounding/tree oracles, cancellation, odd tails, signed zeros, numerical domains,
polynomial accuracy, bounded widening, graph agreement with a CPU HF oracle, cache/batch/padding, candidate mutation,
ties, repetition penalty and error paths. Scratch mutation checks test whether these checks detect deliberate defects.
Cross-device receipts supplement those arguments and do not establish universal hardware or native Windows support.
The source is experimental until graph/operator coverage, native packaging, lifecycle ownership, regeneration and
throughput gates pass. No full FP32 weight shadow may be introduced to make a performance gate pass.

## CUDA kernel implementation (experimental)

`eval/strict_cuda.py` compiles NVRTC kernels that execute this arithmetic sequence: linear projections reading the
FP16 weights in place, RMSNorm, residual add, the SiLU gate, RoPE and causal GQA attention with the specified
softmax. `eval/qwen2_strict_cuda.py` (`qwen2_pairwise_f32_cuda_v1_experimental`) runs the same graph, cache format
and generation rules on them. Primitive operations are inline PTX `add.rn.f32`/`mul.rn.f32` with integer subnormal
flushing. Trees are formed by aligned blocks padded with -0.0, a binary-counter stack, or a barrier-separated
in-place stride tree. Each form equals the adjacent-pair tree above, because x + (-0) == x for finite x. Every
build's PTX and (where `nvdisasm` exists) SASS is audited for contraction, flush modes and vendor arithmetic, and
its NVRTC version, options, architecture and binary hashes are recorded. Bit equality with the eager operations is
tested per kernel and per graph. Receipts and limits: `docs/evidence/2026-10-24-strict-cuda/`. The kernels
remain experimental: no native Windows, lifecycle or packaging gate has passed.
