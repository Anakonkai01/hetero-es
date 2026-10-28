# Experimental vLLM inference for ES

The owner changed the performance priority on 2026-10-25: alternative arithmetic is allowed when it
materially closes the gap to vLLM. This authorizes a separate vendor FP16 execution experiment; historical
noise engines, recipes and receipts remain unchanged. Canonical candidate generation already works over
FP16 storage, so changing noise precision is unnecessary for this experiment.

`eval/vllm_weights.py` maps an unquantized, single-rank dense vLLM model to the canonical HF parameter
names, shapes, order and ties. Q/K/V are disjoint views of `qkv_proj`; gate/up are views of `gate_up_proj`.
Embedding/head views exclude vocabulary padding. A temporary HF template is allocated on meta, and the
returned parameter-only module shares the serving owner's storage. It has no inference forward method.
No second GPU model, FP32 shadow or full prepared-weight copy is created.

Unknown families, sharded/incompatible shapes, non-FP16/noncontiguous storage, unconsumed parameters and
inconsistent weight ties fail. The admitted families are Qwen2, Llama and Mistral; this is layout support,
not general model or hardware qualification. CPU tests independently fuse fixtures and verify canonical
schema, parent/candidate bytes, shared storage, alias preservation, rejection and exact restoration.

`scripts/probe_vllm_es.py` is an explicit GPU, standalone experiment using vLLM's public `LLM.apply_model`
to prepare CPU snapshots and publish canonical candidates. Generation uses ordinary vLLM FP16 kernels.
Prefix caching is disabled and reset after publication; every generation finishes before weights change.
The final restore runs even after a probe failure, and failure is recorded rather than coerced to reward zero.
The script supports one owner in a single process, not distributed or managed execution.

Its identity is `vllm_fp16_canonical_hf_views_es_v1_experimental`, with the existing canonical noise version
reported separately. It does **not** assert B22/FP32-tree arithmetic. Matching weight/candidate hashes do
not imply matching inference tokens or rewards across GPUs. Those differences are measured explicitly.
The installed vLLM version, source pins, complete streams, timing observations and limitations belong in
the evidence, including process-local sampler/compiler settings. No serving package is imported by the
default runtime simply by importing the parameter-view helper.

The separate `Fp16DecoderGraph` v2 also fixes the older experimental merged copies: original HF parameters
now share the merged GEMM allocation, preserving Parameter objects and in-place ES writes. Mixed bias,
external aliases or overlaps retain per-module projection. A changed parameter/storage binding rebuilds
the corresponding merged group. This backend retains strict nonlinears and has its own identity; it is a
useful intermediate speed/control path rather than a vLLM implementation.

Neither path activates a managed worker or changes historical replay policy. See
[`2026-10-25-fast-engine`](../../docs/evidence/2026-10-25-fast-engine/README.md) for the measured scope.
