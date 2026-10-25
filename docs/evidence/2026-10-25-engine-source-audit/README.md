# Engine source audit (2026-10-25)

Owner request: audit and reference vLLM, SGLang and TensorRT-LLM source before continuing the M6
frozen-int8-base/LoRA experiment. This folder records what was read and how it was pinned. The analysis is in
[the audit document](../../strict-engines-source-audit-2026-10-25.md).

## Method

- No engine was installed for this audit. The existing isolated environments and package caches were not modified.
- vLLM source was read from the existing shared sparse clone at
  `/home/pc5070ti/projects/heteroes/.scratch/vllm-source-20261025`, pinned at
  `e7473bf6862289f0647d1f4b01498288b181e063`, with `git show HEAD:<path>`. The clone was not updated or written.
- SGLang source was read from the existing scratch venv at
  `/home/pc5070ti/projects/heteroes/.scratch/sglang-20261024-01/venv/lib/python3.12/site-packages/sglang`,
  package version `0.5.22`. Files were read directly and hashed.
- TensorRT-LLM files were fetched with `curl` from the GitHub raw URLs at tag `v1.2.1` (tag object resolves to commit
  `376f7e1bd8ed543f75014309e3fd4b237e9b0e73`) and stored only in this worktree's ignored `.scratch/` directory.
- Line numbers in the audit refer to the files listed in [SOURCE-INDEX.md](SOURCE-INDEX.md). For vLLM the blob is
  addressed by commit; for SGLang and TensorRT-LLM the SHA-256 of the exact file is recorded.

## Result in one paragraph

All three engines place LoRA after the quantized base projection and add the adapter delta to the base output; the
adapter consumes the original activation, not the quantized one. vLLM and TensorRT-LLM use `cvt.rni.sat.s8.f32`
(ties-even) for activation quantization, SGLang's Triton quantizer uses `libdevice.round` (halfway away from zero).
vLLM and SGLang quantize weights per output channel and activations per token dynamically; TensorRT-LLM has both
weight-only (W8A16) and W8A8-SQ modes. Their prepacking, tiling, split-K and epilogue choices differ, and the recorded
cross-GPU probes already show token differences for vLLM and SGLang. M6 should adopt the base-then-adapter placement
and the prepack-at-load pattern, not the engines' quantization arithmetic.

## What this does NOT show

- TensorRT-LLM was **not** installed, executed, profiled or compared on tokens. Every TensorRT-LLM statement is
  source-only. No speed, memory, accuracy or cross-GPU equality claim is made for it.
- The pinned vLLM source is not proven byte-identical to the vLLM 0.32.0 build measured in
  `../2026-10-24-vllm-probe`; the SGLang wheel's installer records no upstream commit. Hash/commit pins apply to the
  files actually read, not to every build of those versions.
- No claim that the three engines are numerically equivalent, or that any of them satisfies HeteroES's strict
  identity. The source audit explains mechanisms; it does not reproduce or attribute the observed token differences.
- No M6 implementation, oracle, CUDA operator, artifact, graph integration, model-quality result, learning run,
  throughput measurement or acceptance. The M6 constraints in the audit are proposed, not tested or selected.
- No change to the approved M0–M6 objective, the frozen contracts, or the plan SHA-256
  `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.

## Reproduction

```bash
# vLLM: read-only, commit-addressed
git -C /home/pc5070ti/projects/heteroes/.scratch/vllm-source-20261025 rev-parse HEAD
git -C /home/pc5070ti/projects/heteroes/.scratch/vllm-source-20261025 show HEAD:csrc/quantization/w8a8/int8/scaled_quant.cu

# SGLang: installed wheel, hash the exact files
sha256sum /home/pc5070ti/projects/heteroes/.scratch/sglang-20261024-01/venv/lib/python3.12/site-packages/sglang/srt/layers/quantization/w8a8_int8.py

# TensorRT-LLM: fetch a cited file from the pinned commit
curl -sS https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/int8SQ.cu
```

The convenience extracts used while reading are in the ignored worktree scratch
`.scratch/engine-audit-20261025/{vllm-lines.txt,sglang-lines.txt}`. They are not the evidence of record; the
commit- or hash-pinned files in [SOURCE-INDEX.md](SOURCE-INDEX.md) are.
