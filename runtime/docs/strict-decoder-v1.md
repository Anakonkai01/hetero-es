# Experimental strict decoder graph

The strict CUDA implementation is shared by graph adapters, rather than specialized to one checkpoint.
`eval/strict_decoder.py` provides an eager operator oracle and serial CUDA graph;
`eval/strict_decoder_packed.py` packs independent sequences into the same projection and attention launches.
`qwen2_strict_cuda.py` retains the pinned-Qwen compatibility constructor. These remain experimental backends,
with `hardwareQualified: false`; no managed recipe, audit policy or historical numerical identity is changed.

## Admitted graph

The current adapters admit standard `Qwen2ForCausalLM`, `LlamaForCausalLM` and `MistralForCausalLM` graphs with:

- One live FP16 parameter set on one device, dense causal grouped-query attention and default full-dimension RoPE.
- RMSNorm, SiLU-gated MLP, optional linear biases, and either a tied or untied output head.
- Explicit dimensions, including query width different from hidden width. No checkpoint identifier, vocabulary
  size or Qwen-specific hidden/intermediate width selects the arithmetic.
- Context at most 4,096; even head dimensions 2..256; norm width at most 8,192 and projection input width at most
  32,768. These operator bounds do not promise that every admitted batch/model fits a given GPU's memory.

Validation checks family/class, configuration, norm epsilon, every consumed parameter shape and head tying.
Unconsumed parameters, sliding attention, scaled/alternative RoPE, unsupported activations and unknown families
are refused. In particular this does **not** admit every checkpoint named Llama/Mistral, Gemma, MoE, QK-normalized
architectures, quantized weights or attached LoRA. Those require additional operator/graph contracts and tests.

Backend identity includes the graph descriptor, parameter shapes/biases/tying, numerical constants, context and
fixture scope, and source hashes of the shared graph, packed execution, reference operators and CUDA kernels.
Model weight identity remains separate. Per-device NVRTC/options/PTX/SASS/build receipts remain separate from the
portable fingerprint. M4 still has to bind these identities to real qualification, software/OS builds and profiles.

## Arithmetic and execution

The arithmetic remains the [specified reference sequence](strict-reference-v1.md): separate rounded FP32
multiply/add, explicit signed-zero subnormal flushing, adjacent-pair reductions and specified nonlinearities.
Packing changes data placement and independent work scheduling; it does not combine reductions across sequences.

- Linear blocks process bounded row tiles, reuse FP16 weights widened into registers and retain the original
  per-output reduction tree. Coalesced input/weight staging uses padded shared-memory rows to avoid bank conflicts.
  Each staging address has one writer; barriers separate the weight/read/activation phases. Register weights remain
  live while the shared plane is reused. Staging is disabled when its tile exceeds 40 KiB; the original blocked
  path remains available for wider operators. This is bounded workspace, not another model weight set.
- RoPE sine/cosine tables are computed once from canonical frequencies and reference operators. Their explicit
  bound is two FP32 tables of `max_context * head_dim` elements, exposed as buffers for storage inventory.
- Packed attention supplies an independent key offset, key count and causal position for every query. Each query
  executes the same tree and masking rules as its serial reference. Prefill and cached decode share this layout.
- Prefixes and new KV values are packed with two concatenations per layer. Returned per-sequence caches are views
  into bounded slabs. Compaction can temporarily retain a previous slab through a surviving view until the next
  forward; there is no accumulating history of slabs inside the backend.
- Generation supports the reference greedy options, left padding, explicit minimum-ID ties, repetition penalty,
  EOS and compaction. Cache ownership stays local to a generation call and cannot cross candidate mutation.
  The lower-level cache API validates structure, not parent/candidate lineage, just as the original reference did.

## Evidence and remaining work

[Receipts and limits](../../docs/evidence/2026-10-25-strict-throughput/README.md) distinguish three model families,
four small graph layouts and two finite weight states on four physical GPUs from the single trained checkpoint
used for throughput comparison. Tiny graph equality is not acceptance of trained Llama/Mistral checkpoints.

The [vLLM source review](../../docs/STRICT-PERFORMANCE-VLLM.md) identifies which execution techniques transfer and
which arithmetic cannot be substituted. The current scalar strict projections remain substantially slower than
vendor/tensor-core inference. Performance thresholds are not accepted. CUDA Graphs, further projection speed,
paged/bounded persistent KV storage, wider operator/model coverage, native Windows and managed lifecycle/packaging
qualification remain open. The full M0–M6 plan, including unfinished M2 and M6 quantized-base/LoRA, is unchanged.
