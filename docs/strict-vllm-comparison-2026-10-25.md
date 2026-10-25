# HeteroES versus vLLM — measured 2026-10-25

The fastest measured HeteroES **scratch prototype** reaches about half of vLLM default's B1 throughput and one tenth
at B32. It exceeds the surveyed vLLM batch-invariant B1 result, but remains 3.1–3.7x slower than that mode at B32.
The near-vLLM objective is not met. Full M0–M6 remains active.

## Same-workload local 5070 Ti measurements

Units: total output tokens/s. B32 is the aggregate of all 32 sequences. FP16 weight storage; greedy, 32 output
tokens; context limit 512; EOS stopping and prefix reuse disabled. Eight prompts form the pool: B1 uses the first,
B8 uses each once, B32 repeats them four times. One warmup is excluded; report the median of three synchronized host
wall measurements including prefill, decode and host overhead. This is fixed-batch throughput, not a serving SLO test.

| Model | Batch | HeteroES committed B22 | HeteroES faster B22 prototype | vLLM default | vLLM batch-invariant | Default / prototype |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 1 | 177.1 | 249.4 | 529.2 | 173.8 | 2.12x |
| SmolLM2-360M | 8 | 434.3 | 497.9 | 4093.2 | 1371.2 | 8.22x |
| SmolLM2-360M | 32 | 1318.2 | 1451.6 | 14429.4 | 5339.8 | 9.94x |
| TinyLlama-1.1B | 1 | 114.5 | 174.4 | 322.9 | 103.2 | 1.85x |
| TinyLlama-1.1B | 8 | 299.4 | 344.7 | 2330.6 | 825.3 | 6.76x |
| TinyLlama-1.1B | 32 | 830.7 | 918.9 | 7791.8 | 3194.7 | 8.48x |
| Qwen2.5-0.5B | 1 | 171.8 | 254.7 | 518.7 | 146.0 | 2.04x |
| Qwen2.5-0.5B | 8 | 465.1 | 531.3 | 4037.9 | 1164.5 | 7.60x |
| Qwen2.5-0.5B | 32 | 1358.5 | 1507.7 | 13802.5 | 4697.2 | 9.15x |

Committed implementation: `fb18a7b7`; evidence/handoff: `0ba3af41`. The prototype changes weight quantization to an
equivalent exact exponent-bit adjustment plus PTX integer RNE conversion. It remains **unselected**. New tests are
being added before moving it into the implementation. All three preserve a separately versioned integer reference;
this arithmetic is different from the prior FP32 pairwise tree. No managed strict/default activation occurred.

Compared with the preceding captured FP32 backend, prototype B1 improves approximately 1.04x/1.31x/1.21x for
Smol/Tiny/Qwen; B32 improves 1.80x/3.18x/3.01x. These are real gains but do not close the aggregate-compute gap.

## Correctness and measurement limits

- B22 prototype and integer baseline have equal finite prefill hashes, tokens/text/rewards and exact restore on
  all three trained models for parent, canonical seed 7001 at ±sigma 1e-3, and restored parent. B22 also matches the
  prior tree's tokens on this corpus. **B14 changes one Qwen minus-candidate stream**; that counterexample is retained.
- Selected-source regression: 301 tests per run on each of four GPUs; 3016 runtime CPU passed / 285 skipped,
  452 backend passed, full check-all and Linux packaging passed; 11/11 scratch mutations killed. These include
  independent CPU rational oracles. Prototype weight quantization exhausts 1,017,852 admitted finite FP16
  value/row-exponent pairs per precision on 5070 Ti and 3060, plus 99 reference/operator/decoder checks per target.
- Selected Smol/Qwen parent/canonical-candidate logits, token/text/reward and weight hashes match between local
  5070 Ti and Thao 3060. The faster prototype's trained measurements above are local. Native Windows, full managed
  lifecycle/ownership, general model quality and universal heterogeneous acceptance remain open.
- vLLM 0.32.0 uses a separate Torch/CUDA/Transformers environment. GPUs are unisolated and receipts come from
  separate measurement stages. Prompt/workload/consumed model assets match. Old Smol full manifests include extra
  HF download metadata; comparison excludes it only for asset equality and explicitly retains full-manifest inequality.
- vLLM batch-invariant is a distinct measured configuration, not a demonstrated substitute for this project's
  heterogeneous strict contract. No serving concurrency, long-context, long-output or end-to-end ES claim follows
  from the fixed-batch table.

The remaining performance targets are on-the-fly integer packing, projection tile/data reuse and duplicated
activation quantization. Earlier random-layout profiles identified projections as dominant; those percentages must
be remeasured on the faster trained decoder before choosing its next bottleneck. More scheduling alone cannot be
assumed to explain this fixed-batch gap.

## Exact receipts

- [Selected results and prior receipt paths](evidence/2026-10-25-strict-integer/RESULTS-01.md),
  [asserted baseline comparisons](evidence/2026-10-25-strict-integer/trained-comparison-01.json).
- [Prototype results](evidence/2026-10-25-strict-integer/CVT-RESULTS-01.md),
  [asserted prototype comparisons](evidence/2026-10-25-strict-integer/cvt-trained-comparison-01.json).
- Prototype timing files: [Smol](evidence/2026-10-25-strict-integer/bench-cvt-smol-b22-nhan-01.json),
  [TinyLlama](evidence/2026-10-25-strict-integer/bench-cvt-tiny-b22-nhan-01.json),
  [Qwen](evidence/2026-10-25-strict-integer/bench-cvt-qwen-b22-nhan-01.json).
- vLLM default: [Smol](evidence/2026-10-25-strict-overnight/bench-smollm-vllm-nhan-01.json),
  [TinyLlama](evidence/2026-10-25-strict-overnight/bench-tinyllama-vllm-nhan-01.json),
  [Qwen](evidence/2026-10-25-strict-throughput/bench-vllm-nhan-01.json).
- vLLM batch-invariant: [Smol](evidence/2026-10-25-strict-overnight/bench-smollm-invariant-nhan-01.json),
  [TinyLlama](evidence/2026-10-25-strict-overnight/bench-tinyllama-invariant-nhan-01.json),
  [Qwen](evidence/2026-10-25-strict-throughput/bench-vllm-invariant-nhan-01.json).
