# Source index — engine audit 2026-10-25

Every line citation in [the audit](../../strict-engines-source-audit-2026-10-25.md) resolves through this file.
Hashes identify the exact content read, not a version range.

## Pins

| Engine | Pin | Verification |
| --- | --- | --- |
| vLLM | commit `e7473bf6862289f0647d1f4b01498288b181e063` | `git -C .../vllm-source-20261025 rev-parse HEAD`; sparse worktree, read-only |
| SGLang | wheel `sglang==0.5.22`, `sglang_kernel==0.4.9` | `sglang-0.5.22.dist-info/METADATA`; no `direct_url.json`, so no upstream commit is recorded |
| TensorRT-LLM | tag `v1.2.1` → commit `376f7e1bd8ed543f75014309e3fd4b237e9b0e73` | GitHub API `git/ref/tags/v1.2.1` returned a commit object with that SHA |

## vLLM

Base URL for links:
`https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/`

| Path | Git blob SHA-1 | Lines | Lines cited | What it supports |
| --- | --- | ---: | --- | --- |
| `csrc/quantization/w8a8/int8/scaled_quant.cu` | `e620c1818475cdb803b2e5c893ae4be443049ec3` | 333 | 10-37, 142-177 | `cvt.rni.sat.s8.f32`; row `absmax/127`; zero-row reciprocal scale |
| `csrc/quantization/w8a8/cutlass/Epilogues.md` | `15a66913e97a3279e74f984b84aba017f1e8c7aa` | 168 | 22-67 | `D = s_a s_b D_hat + bias`; symmetric weights, optional activation zero point |
| `vllm/model_executor/kernels/linear/scaled_mm/cutlass.py` | `2d4c5fecbdbc38625d4bd049eaba6c381abd51d7` | 335 | 46-56, 122-154 | transpose at load; dynamic quant then `cutlass_scaled_mm` |
| `vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_w8a8_int8.py` | `860b78b18711308acbcfe81f09d5721ea6794f58` | 113 | 71-83 | `(N,1)` FP32 weight scale |
| `vllm/model_executor/kernels/linear/mixed_precision/marlin.py` | `60687fc8602ddfd66d079f73119d08369fd23a84` | 201 | 100-143 | weight/scale repack once at load |
| `vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_wNa16.py` | `5667f2726b7ad50b2c7bf6a78bbe94a09b1f3281` | 290 | 79-82 | Marlin tiling depends on batch; batch-invariant fallback |
| `vllm/model_executor/determinism/batch_invariant.py` | `589452c751419c4afacf4ab2c43db8195ea7c996` | 1443 | 100-137 | FP32 accumulator `tl.dot` in the batch-invariant matmul |
| `vllm/lora/layers/base_linear.py` | `12888cf3db3d6ca7beabdf20f66c14c8dfcdcc40` | 331 | 215-232, 256-300 | base output then LoRA add; dual-stream variant |

Links:
[scaled_quant.cu:10-37](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/csrc/quantization/w8a8/int8/scaled_quant.cu#L10-L37) ·
[142-177](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/csrc/quantization/w8a8/int8/scaled_quant.cu#L142-L177) ·
[Epilogues.md:22-67](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/csrc/quantization/w8a8/cutlass/Epilogues.md#L22-L67) ·
[cutlass.py:46-56](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/kernels/linear/scaled_mm/cutlass.py#L46-L56) ·
[cutlass.py:122-154](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/kernels/linear/scaled_mm/cutlass.py#L122-L154) ·
[W8A8 schema:71-83](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_w8a8_int8.py#L71-L83) ·
[marlin.py:100-143](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/kernels/linear/mixed_precision/marlin.py#L100-L143) ·
[wNa16.py:79-82](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/layers/quantization/compressed_tensors/schemes/compressed_tensors_wNa16.py#L79-L82) ·
[batch_invariant.py:100-137](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/model_executor/determinism/batch_invariant.py#L100-L137) ·
[base_linear.py:215-232](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/lora/layers/base_linear.py#L215-L232) ·
[base_linear.py:256-300](https://github.com/vllm-project/vllm/blob/e7473bf6862289f0647d1f4b01498288b181e063/vllm/lora/layers/base_linear.py#L256-L300)

## SGLang 0.5.22

Installed prefix (scratch venv, read-only):
`/home/pc5070ti/projects/heteroes/.scratch/sglang-20261024-01/venv/lib/python3.12/site-packages/sglang/`

| Path | SHA-256 | Lines | Lines cited | What it supports |
| --- | --- | ---: | --- | --- |
| `srt/layers/quantization/w8a8_int8.py` | `37f8b6a5eb286a6051f49ff26dddf2212bd2fa8d27a57bd9f08da6bc6aa5f4b0` | 384 | 64-69, 224-231 | per-channel symmetric weights, per-token activations; `int8_scaled_mm` |
| `kernels/ops/quantization/int8_kernel.py` | `83ec5f7efc8cb17f794b8fb08c2ce668270012847868706202a87f59bd53abd5` | 209 | 21-55 | `absmax/127`, `1e-10` floor, `libdevice.round` |
| `kernels/ops/gemm/int8_kernel.py` | `c98ec294d6259b904764bbe787185935889ea3425613a1a59f4ae30814e51791` | 229 | 73-85 | per-K-block scale applied inside the FP32 accumulation |
| `srt/lora/layers.py` | `ac84622c5712e8b75d56767f6984809c9ed8263ab9e1299ec33e59ee9baa5bbb` | 1363 | 482-509 | base quant method then LoRA on the original input |
| `srt/lora/trtllm_lora_temp/attention.py` | `7f746c0e887cd6efd8307da1df91d30358ea7a81793361ed03aa92a15112ab9c` | 282 | 31-75 | side-stream LoRA-A shrink, expand after base GEMM rejoin |

Package metadata:
`sglang-0.5.22.dist-info/METADATA` (`Name: sglang`, `Version: 0.5.22`), `INSTALLER` = `uv`, no `direct_url.json`.

## TensorRT-LLM v1.2.1 (source only)

Commit: `376f7e1bd8ed543f75014309e3fd4b237e9b0e73`.
Base URL for links:
`https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/`

| Path | SHA-256 | Lines | Lines cited | What it supports |
| --- | --- | ---: | --- | --- |
| `tensorrt_llm/quantization/mode.py` | `17779b0ec19b3f0a08d36ea01871a9a4cb940c3470308eca1b0bf486845f3d9e` | 479 | 23-56 | W8A16 / W8A8-SQ plugin modes |
| `tensorrt_llm/_torch/modules/linear.py` | `d5c96a4a18bdf0879653173bfe815b27240100e198d5770805709837357d04a2` | 2356 | 156-166, 1499-1532, 2266-2276 | preprocess at load; int8 `(in,out)` + per-output scale; base then LoRA |
| `tensorrt_llm/layers/linear.py` | `38a9a55a6aadbadd96b9abccfeb8681eb6cd29d1f5e5ea54803a5fb3b530af77` | 551 | 226-269 | base matmul then `+ self.lora(...)` |
| `cpp/tensorrt_llm/common/cudaTypeUtils.cuh` | `1441d8f3eae5c3d4305fd57850d5572f846bdf87f35c6793a5945330557254a9` | 754 | 366-375 | int8 conversion uses `cvt.rni.sat.s8.f32` |
| `cpp/tensorrt_llm/kernels/quantization.cuh` | `e6367fb789428a57e00eca78b4bbc51c59249415c06e9c08189ad63d1aa38a4a` | 908 | 222-271 | `1e-6` row floor, `max/127`, reciprocal multiply |
| `cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/int8SQ.cu` | `88e596210dc1e1ed16d2514ddf9a5aa1ab6454ca0193f1587d20fde470546ec3` | 177 | 26-120, 134-166 | `__dp4a` int32 accumulator; per-channel/per-token epilogue; small-M dispatch |
| `cpp/tensorrt_llm/kernels/cutlass_kernels/cutlass_preprocessors.cpp` | `7be12a8a3d6276a71bd0e291d977cf2ddb90cab277e754f8a15aef2d0088163c` | 825 | 418-438, 570-628, 735-741 | +128 biased int8 storage; transpose/interleave at load; host `round()` and clip |
| `cpp/tensorrt_llm/kernels/cutlass_kernels/fpA_intB_gemm/fpA_intB_gemm_template.h` | `1ea03a51140a62518604731a8d9d89de5fb4abdeda45921c44b3fffa09cf3dd6` | 609 | 60-98 | mixed activation/weight GEMM family |
| `cpp/tensorrt_llm/kernels/lora/lora.cpp` | `75cef6f5c4b94d05f5d585455166bad31a84423df21af5d4afc7ad8eb9716c66` | 347 | 323-330 | split-K first LoRA GEMM |
| `cpp/tensorrt_llm/kernels/lora/lora.h` | `32c319d17ade0108af853cc35f1f902b622656606e9e3e905c0079c33d27d0b6` | 78 | 67 | `mSplitKSlices = 16` |

Links:
[mode.py:23-56](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/tensorrt_llm/quantization/mode.py#L23-L56) ·
[torch linear:156-166](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/tensorrt_llm/_torch/modules/linear.py#L156-L166) ·
[torch linear:1499-1532](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/tensorrt_llm/_torch/modules/linear.py#L1499-L1532) ·
[torch linear:2266-2276](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/tensorrt_llm/_torch/modules/linear.py#L2266-L2276) ·
[layers linear:226-269](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/tensorrt_llm/layers/linear.py#L226-L269) ·
[cudaTypeUtils.cuh:366-375](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/common/cudaTypeUtils.cuh#L366-L375) ·
[quantization.cuh:222-271](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/quantization.cuh#L222-L271) ·
[int8SQ.cu:26-120](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/int8SQ.cu#L26-L120) ·
[int8SQ.cu:134-166](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/int8SQ.cu#L134-L166) ·
[cutlass_preprocessors.cpp:418-438](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/cutlass_kernels/cutlass_preprocessors.cpp#L418-L438) ·
[570-628](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/cutlass_kernels/cutlass_preprocessors.cpp#L570-L628) ·
[735-741](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/cutlass_kernels/cutlass_preprocessors.cpp#L735-L741) ·
[fpA_intB_gemm_template.h:60-98](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/cutlass_kernels/fpA_intB_gemm/fpA_intB_gemm_template.h#L60-L98) ·
[lora.cpp:323-330](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/lora/lora.cpp#L323-L330) ·
[lora.h:67](https://github.com/NVIDIA/TensorRT-LLM/blob/376f7e1bd8ed543f75014309e3fd4b237e9b0e73/cpp/tensorrt_llm/kernels/lora/lora.h#L67)

Supplementary files fetched and hashed but not cited line-by-line:

| Path | SHA-256 | Purpose |
| --- | --- | --- |
| `cpp/tensorrt_llm/kernels/quantization.cu` | `5d248e936c3241e08ec99a59b6ac2e67ca3a4adf64e094a21dfb21a49868b4d1` | per-tensor quantized-kernel wrappers |
| `tensorrt_llm/_torch/peft/lora/layer.py` | `66b8f98564a05e368ceb88424054f43dbeab66bca13fa0c421dc6e8684710739` | LoRA module/grouped-GEMM call site |
| `cpp/tensorrt_llm/common/quantTypeUtils.cuh` | `bab54c759ab4109d21f416b52e4788cc1bc3bacec1bfc850f289d0c37934ddc2` | int8 quant type limits |
| `cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/details.h` | `9190c67f99e9bd3a34721fa30e25fb178fda284dea6482b417be1312ddfd3279` | weight-only type details |
| `cpp/tensorrt_llm/kernels/weightOnlyBatchedGemv/common.h` | `0bf817c6087f1e0526d10c210df8400c7f2a9bc84d1eabde059532563e58ff2f` | weight-only common declarations |
